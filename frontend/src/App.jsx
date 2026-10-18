import { useState } from "react";
import AppShell from "./components/AppShell.jsx";
import AutomationsPage from "./pages/AutomationsPage.jsx";
import ConnectionsPage from "./pages/ConnectionsPage.jsx";
import InvestigationPage from "./pages/InvestigationPage.jsx";
import LocalLogPage from "./pages/LocalLogPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

export default function App() {
  const [page, setPage] = useState("investigacao");
  const [detailTab, setDetailTab] = useState("chat");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [canvasOpen, setCanvasOpen] = useState(true);

  return (
    <AppShell
      page={page}
      sidebarOpen={sidebarOpen}
      canvasOpen={canvasOpen}
      onNavigate={setPage}
      onToggleSidebar={() => setSidebarOpen((open) => !open)}
      onToggleCanvas={() => setCanvasOpen((open) => !open)}
    >
      {page === "investigacao" ? (
        <InvestigationPage detailTab={detailTab} onDetailTab={setDetailTab} />
      ) : null}
      {page === "automacoes" ? <AutomationsPage /> : null}
      {page === "log" ? <LocalLogPage /> : null}
      {page === "conexoes" ? <ConnectionsPage /> : null}
      {page === "configuracoes" ? <SettingsPage /> : null}
    </AppShell>
  );
}
