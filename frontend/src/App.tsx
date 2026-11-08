import { Route, Routes } from "react-router-dom";
import { MonitorProvider } from "./state/MonitorContext";
import { Header } from "./components/layout/Header";
import { AlertBanner, AlertToasts } from "./components/layout/Alerts";
import { Dashboard } from "./pages/Dashboard";
import { Security } from "./pages/Security";
import { Settings } from "./pages/Settings";
import { Cooling } from "./pages/Cooling";

export default function App() {
  return (
    <MonitorProvider>
      <div className="min-h-screen">
        <Header />
        <AlertBanner />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/cooling" element={<Cooling />} />
          <Route path="/security" element={<Security />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Dashboard />} />
        </Routes>
        <AlertToasts />
      </div>
    </MonitorProvider>
  );
}
