import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { LoginScreen } from './pages/LoginScreen';
import { DashboardScreen } from './pages/DashboardScreen';
import { UploadScreen } from './pages/UploadScreen';
import { SessionDetailScreen } from './pages/SessionDetailScreen';
import { BenchmarkScreen } from './pages/BenchmarkScreen';
import { LiveStreamScreen } from './pages/LiveStreamScreen';
import { getAuthToken, removeAuthToken } from './api';

export const App: React.FC = () => {
  const [token, setToken] = useState<string | null>(getAuthToken());
  const [currentTab, setCurrentTab] = useState<string>('dashboard');
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  useEffect(() => {
    const handleAuthError = () => {
      setToken(null);
      setCurrentTab('login');
    };

    window.addEventListener('ripguard_auth_error', handleAuthError);
    return () => window.removeEventListener('ripguard_auth_error', handleAuthError);
  }, []);

  useEffect(() => {
    if (!token && currentTab !== 'benchmark') {
      setCurrentTab('login');
    }
  }, [token, currentTab]);

  const handleLoginSuccess = () => {
    setToken(getAuthToken());
    setCurrentTab('dashboard');
  };

  const handleLogout = () => {
    removeAuthToken();
    setToken(null);
    setCurrentTab('login');
  };

  const handleSelectSession = (id: string) => {
    setSelectedSessionId(id);
    setCurrentTab('detail');
  };

  const handleSessionCreated = (id: string) => {
    setSelectedSessionId(id);
    setCurrentTab('detail');
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100">
      <Navbar
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        isLoggedIn={!!token}
        onLogout={handleLogout}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {currentTab === 'login' && <LoginScreen onLoginSuccess={handleLoginSuccess} />}

        {currentTab === 'dashboard' && (
          <DashboardScreen
            onSelectSession={handleSelectSession}
            onNewAnalysis={() => setCurrentTab('upload')}
          />
        )}

        {currentTab === 'upload' && (
          <UploadScreen
            onSessionCreated={handleSessionCreated}
            onCancel={() => setCurrentTab('dashboard')}
          />
        )}

        {currentTab === 'detail' && selectedSessionId && (
          <SessionDetailScreen
            sessionId={selectedSessionId}
            onBack={() => setCurrentTab('dashboard')}
          />
        )}

        {currentTab === 'benchmark' && <BenchmarkScreen />}

        {currentTab === 'stream' && <LiveStreamScreen />}
      </main>

      <footer className="border-t border-slate-900 bg-slate-950/80 py-6 text-center text-xs text-slate-600">
        RipGuard — Computer Vision Beach Safety Decision-Support System • CVPR 2025 RipVIS Benchmark
      </footer>
    </div>
  );
};

export default App;
