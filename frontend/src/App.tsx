import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { LoginPage } from './auth/LoginPage';
import { SignupPage } from './auth/SignupPage';
import { RequireAuth } from './auth/RequireAuth';
import {
  AppShell,
  ChatSessionPlaceholder,
  EmptyHomePlaceholder,
} from './shell/AppShell';
import { SessionsProvider } from './sessions/SessionsProvider';

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route
            element={
              <RequireAuth>
                <SessionsProvider>
                  <AppShell />
                </SessionsProvider>
              </RequireAuth>
            }
          >
            <Route path="/" element={<EmptyHomePlaceholder />} />
            <Route path="/c/:sessionId" element={<ChatSessionPlaceholder />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
