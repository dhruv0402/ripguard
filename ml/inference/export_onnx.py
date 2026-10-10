"""
Export trained PyTorch checkpoints to ONNX format with dynamic batching.
Supports both 3-channel (appearance) and 5-channel (optical flow) models.

Usage:
    .venv/bin/python ml/inference/export_onnx.py --checkpoint ml/checkpoints/ripguard_unet_best.pt --output ml/checkpoints/ripguard_unet_best.onnx
"""

import argparse
import os
import torch
import segmentation_models_pytorch as smp
import onnx
import onnxruntime as ort
import numpy as np


def export_checkpoint_to_onnx(checkpoint_path: str, output_path: str, img_size: int = 512):
    print(f"Loading checkpoint: {checkpoint_path}")
    state_dict = torch.load(checkpoint_path, map_location="cpu")
    
    first_weight = state_dict.get("encoder.conv1.weight", None)
    in_channels = first_weight.shape[1] if first_weight is not None else 3
    print(f"Detected in_channels: {in_channels}")

    model = smp.create_model(
        arch="Unet",
        encoder_name="resnet34",
        encoder_weights=None,
        in_channels=in_channels,
        classes=1,
    )
    model.load_state_dict(state_dict)
    model.eval()

    dummy_input = torch.randn(1, in_channels, img_size, img_size, dtype=torch.float32)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    print(f"Exporting to ONNX: {output_path}")

    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size"},
            "output": {0: "batch_size"},
        },
    )

    # Validate ONNX model
    onnx_model = onnx.load(output_path)
    onnx.checker.check_model(onnx_model)
    print("ONNX model structure checked successfully.")

    # Validate with onnxruntime
    session = ort.InferenceSession(output_path, providers=["CPUExecutionProvider"])
    ort_inputs = {session.get_inputs()[0].name: dummy_input.numpy()}
    ort_outs = session.run(None, ort_inputs)

    with torch.no_grad():
        torch_out = model(dummy_input).numpy()

    np.testing.assert_allclose(torch_out, ort_outs[0], rtol=1e-03, atol=1e-05)
    print(f"Verified ONNX vs PyTorch parity. Model exported cleanly to {output_path} ({os.path.getsize(output_path) / (1024*1024):.2f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export PyTorch checkpoint to ONNX")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to .pt checkpoint")
    parser.add_argument("--output", type=str, required=True, help="Path to save .onnx file")
    parser.add_argument("--img_size", type=int, default=512, help="Input spatial dimension")
    args = parser.parse_args()

    export_checkpoint_to_onnx(args.checkpoint, args.output, args.img_size)
