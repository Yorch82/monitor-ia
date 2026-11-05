import { Route, Routes } from "react-router-dom";
import { MonitorProvider } from "./state/MonitorContext";
import { Header } from "./components/layout/Header";
import { AlertBanner, AlertToasts } from "./components/layout/Alerts";
import { Dashboard } from "./pages/Dashboard";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <MonitorProvider>
      <div className="min-h-screen">
        <Header />
        <AlertBanner />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Dashboard />} />
        </Routes>
        <AlertToasts />
      </div>
    </MonitorProvider>
  );
}
