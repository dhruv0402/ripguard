"""
RipGuard Edge Hardware Acceleration & TensorRT FP16 Compiler
Designed for physical lifeguard tower edge nodes running NVIDIA Jetson Orin boards
(Jetson Orin Nano / NX / AGX Orin).

Key Objectives:
  1. Compile ONNX model checkpoints (e.g., ripguard_motion_unet_best.onnx) to TensorRT FP16 engines.
  2. Achieve sustained >= 30 FPS throughput for real-time coastal rip current detection.
  3. Enforce sub-20W power dissipation envelope (Jetson Orin 15W / 20W operational modes)
     suitable for solar and PoE beach tower installations.
  4. Provide latency profiling (p50, p95, p99), memory usage, and edge deployment verification.
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import time
import tempfile
from typing import Dict, Any, Tuple, Optional
import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None

try:
    # pyrefly: ignore[missing-import]
    import tensorrt as trt
except ImportError:
    trt = None

logger = logging.getLogger("ripguard.edge_optimizer")


class EdgeOptimizer:
    """
    Manages ONNX to TensorRT FP16 compilation and latency benchmarking
    for NVIDIA Jetson Orin edge deployments.
    """

    JETSON_ORIN_ARCH = "sm_87"
    TARGET_FPS = 30.0
    TARGET_POWER_BUDGET_WATTS = 20.0  # Sub-20W power envelope

    def __init__(
        self,
        onnx_path: str = "ml/checkpoints/ripguard_motion_unet_best.onnx",
        engine_output_path: Optional[str] = None,
        precision: str = "FP16",
        max_workspace_mb: int = 1024,
        input_shape: Tuple[int, ...] = (1, 5, 512, 512),
    ):
        self.onnx_path = onnx_path
        if engine_output_path:
            self.engine_path = engine_output_path
        else:
            base, _ = os.path.splitext(onnx_path)
            self.engine_path = f"{base}_jetson_fp16.engine"

        self.precision = precision.upper()
        self.max_workspace_mb = max_workspace_mb
        self.input_shape = input_shape
        self.metadata_path = f"{self.engine_path}.meta.json"

    def detect_edge_capabilities(self) -> Dict[str, Any]:
        """Detects available hardware accelerators, Jetson Orin environments, and providers."""
        providers = ort.get_available_providers() if ort else []
        has_trt_native = trt is not None
        has_trtexec = shutil.which("trtexec") is not None or os.path.exists("/usr/src/tensorrt/bin/trtexec")
        has_trt_provider = "TensorrtExecutionProvider" in providers
        has_cuda_provider = "CUDAExecutionProvider" in providers

        # Check if running on NVIDIA Jetson Linux (Tegra)
        is_tegra = os.path.exists("/etc/nv_tegra_release")

        return {
            "is_jetson_tegra": is_tegra,
            "has_native_tensorrt": has_trt_native,
            "has_trtexec_cli": has_trtexec,
            "has_trt_ort_provider": has_trt_provider,
            "has_cuda_provider": has_cuda_provider,
            "available_ort_providers": providers,
            "target_architecture": "NVIDIA Jetson Orin (Ampere sm_87)",
            "target_power_profile": f"Sub-{int(self.TARGET_POWER_BUDGET_WATTS)}W (Jetson Orin 15W/20W Mode)",
            "target_fps": self.TARGET_FPS,
            "precision": self.precision,
        }

    def compile_onnx_to_tensorrt(
        self,
        force_recompile: bool = False,
    ) -> Dict[str, Any]:
        """Compile with a real TensorRT backend; never substitute a placeholder.

        Engines are rebuilt on every call (``force_recompile`` is retained for
        caller compatibility). Existing files are not trusted as build evidence.
        """
        if not os.path.isfile(self.onnx_path):
            return self._unavailable("Source ONNX checkpoint not found")
        caps = self.detect_edge_capabilities()
        if not caps["has_native_tensorrt"] and not caps["has_trtexec_cli"]:
            return self._unavailable("No native TensorRT compiler or trtexec available")
        t0 = time.perf_counter()
        temporary_path = None
        method = "native_tensorrt_api" if caps["has_native_tensorrt"] else "trtexec_cli"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.engine_path)), exist_ok=True)
            # A failed build must not turn an old file into a successful result.
            with tempfile.NamedTemporaryFile(
                dir=os.path.dirname(os.path.abspath(self.engine_path)),
                suffix=".engine", delete=False,
            ) as temporary:
                temporary_path = temporary.name
            if caps["has_native_tensorrt"]:
                trt_logger = trt.Logger(trt.Logger.INFO)
                builder = trt.Builder(trt_logger)
                flags = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
                network = builder.create_network(flags)
                parser = trt.OnnxParser(network, trt_logger)
                with open(self.onnx_path, "rb") as source:
                    if not parser.parse(source.read()):
                        errors = [str(parser.get_error(i)) for i in range(parser.num_errors)]
                        raise RuntimeError(f"TensorRT ONNX parsing failed: {errors}")
                config = builder.create_builder_config()
                config.set_memory_pool_limit(
                    trt.MemoryPoolType.WORKSPACE, self.max_workspace_mb * 1024 * 1024
                )
                if self.precision == "FP16":
                    config.set_flag(trt.BuilderFlag.FP16)
                serialized_engine = builder.build_serialized_network(network, config)
                if serialized_engine is None:
                    raise RuntimeError("TensorRT failed to build serialized engine")
                with open(temporary_path, "wb") as output:
                    output.write(serialized_engine)
            else:
                cmd = [
                    shutil.which("trtexec") or "/usr/src/tensorrt/bin/trtexec",
                    f"--onnx={self.onnx_path}", f"--saveEngine={temporary_path}",
                    f"--memPoolSize=workspace:{self.max_workspace_mb}MiB",
                ]
                if self.precision == "FP16":
                    cmd.append("--fp16")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                if result.returncode != 0:
                    raise RuntimeError(f"trtexec failed: {result.stderr}")
            if os.path.getsize(temporary_path) == 0:
                raise RuntimeError("Compiler did not produce a nonempty engine")
            os.replace(temporary_path, self.engine_path)
            meta = {
                "status": "COMPILED", "compilation_method": method,
                "onnx_source": self.onnx_path, "engine_path": self.engine_path,
                "precision": self.precision, "workspace_mb": self.max_workspace_mb,
                "input_shape": list(self.input_shape), "target_fps": self.TARGET_FPS,
                "power_consumption_w": None, "sub_20w_certified": False,
                "field_trial_ready": False,
                "compilation_time_sec": time.perf_counter() - t0,
                "timestamp": time.time(),
            }
            with open(self.metadata_path, "w") as output:
                json.dump(meta, output, indent=2)
            return meta
        except Exception as exc:
            return self._unavailable(str(exc), status="FAILED", compilation_method=method)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def _unavailable(self, reason: str, status: str = "UNAVAILABLE", **extra) -> Dict[str, Any]:
        return {
            "status": status, "reason": reason, "onnx_source": self.onnx_path,
            "power_consumption_w": None, "sub_20w_certified": False,
            "field_trial_ready": False, **extra,
        }

    def benchmark_edge_throughput(
        self,
        iterations: int = 50,
        warmup: int = 5,
    ) -> Dict[str, Any]:
        """
        Profiles inference latency and sustained FPS for the model.
        Reports mean, median (p50), 95th percentile (p95), and sustained FPS.
        """
        if not os.path.isfile(self.onnx_path):
            return self._unavailable("ONNX model not found")
        if ort is None:
            return self._unavailable("ONNX Runtime is not installed")
        if iterations <= 0 or warmup < 0:
            return self._unavailable("iterations must be positive and warmup nonnegative", status="FAILED")

        providers = ["CPUExecutionProvider"]
        if ort:
            available = ort.get_available_providers()
            if "TensorrtExecutionProvider" in available:
                providers.insert(0, ("TensorrtExecutionProvider", {
                    "trt_fp16_enable": True,
                    "trt_max_workspace_size": self.max_workspace_mb * 1024 * 1024,
                }))
            elif "CUDAExecutionProvider" in available:
                providers.insert(0, "CUDAExecutionProvider")
            elif "CoreMLExecutionProvider" in available:
                providers.insert(0, "CoreMLExecutionProvider")

        try:
            dummy_input = np.zeros(self.input_shape, dtype=np.float32)

            session = ort.InferenceSession(self.onnx_path, providers=providers)
            input_name = session.get_inputs()[0].name

            # Warmup iterations
            for _ in range(warmup):
                session.run(None, {input_name: dummy_input})

            latencies_ms = []
            for _ in range(iterations):
                t0 = time.perf_counter()
                session.run(None, {input_name: dummy_input})
                latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        except Exception as exc:
            return self._unavailable(str(exc), status="FAILED")

        latencies_arr = np.array(latencies_ms)
        mean_lat = float(np.mean(latencies_arr))
        p50 = float(np.percentile(latencies_arr, 50))
        p95 = float(np.percentile(latencies_arr, 95))
        p99 = float(np.percentile(latencies_arr, 99))
        host_fps = round(1000.0 / max(mean_lat, 0.001), 1)

        session_providers = session.get_providers()
        return {
            "status": "BENCHMARKED",
            # ORT provider order is preference, not per-node placement evidence.
            "active_provider": session_providers[0],
            "session_providers": session_providers,
            "provider_note": "Session providers; individual nodes may use fallback providers",
            "host_measured_latency_ms": {
                "mean": mean_lat, "p50": p50, "p95": p95, "p99": p99,
            },
            "host_fps": host_fps,
            "iterations": iterations, "warmup": warmup,
            "meets_30fps_target": host_fps >= self.TARGET_FPS,
            "power_consumption_w": None,
            "sub_20w_certified": False,
            "field_trial_ready": False,
        }


def optimize_for_jetson_orin(
    onnx_path: str = "ml/checkpoints/ripguard_motion_unet_best.onnx",
    output_engine: Optional[str] = None,
    benchmark: bool = True,
) -> Dict[str, Any]:
    """Helper entry point for compilation and benchmarking."""
    optimizer = EdgeOptimizer(onnx_path=onnx_path, engine_output_path=output_engine)
    compile_meta = optimizer.compile_onnx_to_tensorrt()
    results = {"compilation": compile_meta}

    if benchmark:
        bench_results = optimizer.benchmark_edge_throughput(iterations=10, warmup=2)
        results["benchmark"] = bench_results

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RipGuard Jetson Orin TensorRT FP16 Edge Optimizer")
    parser.add_argument("--onnx", type=str, default="ml/checkpoints/ripguard_motion_unet_best.onnx")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--fp16", action="store_true", default=True)
    parser.add_argument("--benchmark", action="store_true", default=True)
    args = parser.parse_args()

    res = optimize_for_jetson_orin(args.onnx, args.output, benchmark=args.benchmark)
    print(json.dumps(res, indent=2))
