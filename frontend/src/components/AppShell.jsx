import CanvasPanel from "./CanvasPanel.jsx";
import Sidebar from "./Sidebar.jsx";
import TopBar from "./TopBar.jsx";

export default function AppShell({
  page,
  sidebarOpen,
  canvasOpen,
  onNavigate,
  onToggleSidebar,
  onToggleCanvas,
  children,
}) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-forge-bg text-forge-text">
      <TopBar
          sidebarOpen={sidebarOpen}
          canvasOpen={canvasOpen}
          onToggleSidebar={onToggleSidebar}
          onToggleCanvas={onToggleCanvas}
          onOpenSettings={() => onNavigate("configuracoes")}
        />
        <div className="flex min-h-0 flex-1">
          {sidebarOpen ? <Sidebar page={page} onNavigate={onNavigate} /> : null}
          <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:flex-row">
            <main className="min-w-0 flex-1 overflow-auto p-4">{children}</main>
            {canvasOpen ? <CanvasPanel onClose={onToggleCanvas} /> : null}
          </div>
        </div>
      </div>
  );
}
