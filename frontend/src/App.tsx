import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { useAuth } from "@/lib/auth";
import { AppLayout } from "@/components/AppLayout";
import { RequireDataSource } from "@/components/RequireDataSource";

import Landing from "@/pages/public/Landing";
import Login from "@/pages/public/Login";
import Register from "@/pages/public/Register";

import Dashboard from "@/pages/Dashboard";
import Documents from "@/pages/Documents";
import Obligations from "@/pages/Obligations";
import Approvals from "@/pages/Approvals";
import ChangeRequests from "@/pages/ChangeRequests";
import Compliance from "@/pages/Compliance";

import Audit from "@/pages/Audit";
import Settings from "@/pages/Settings";

function Protected({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="grid min-h-screen place-items-center text-ink-400">Loading…</div>;
  if (!user) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  const location = useLocation();
  const { user } = useAuth();

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={user ? <Navigate to="/app" replace /> : <Login />} />
        {/* No reactive guard here: registration authenticates mid-flow (after the
            firm is created) and must stay mounted to show the Connect-data step.
            Register handles redirecting users who were already logged in on arrival. */}
        <Route path="/register" element={<Register />} />

        <Route
          path="/app"
          element={
            <Protected>
              <AppLayout />
            </Protected>
          }
        >
          <Route index element={<Navigate to="documents" replace />} />
          <Route path="overview" element={<Dashboard />} />
          <Route path="documents" element={<Documents />} />
          <Route path="obligations" element={<Obligations />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="change-requests" element={<RequireDataSource><ChangeRequests /></RequireDataSource>} />
          <Route path="compliance" element={<RequireDataSource><Compliance /></RequireDataSource>} />
          <Route path="audit" element={<Audit />} />
          <Route path="settings" element={<Settings />} />
        </Route>


        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  );
}
