import Button from "./Button.jsx";
import { IconMark, IconPanel, IconUser } from "./icons.jsx";

export default function TopBar({
  sidebarOpen,
  canvasOpen,
  onToggleSidebar,
  onToggleCanvas,
  onOpenSettings,
}) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-forge-line bg-forge-panel px-3">
      <span className="flex items-center gap-2 pr-2">
        <span className="flex size-7 items-center justify-center rounded-md bg-forge-blue text-white">
          <IconMark className="size-4" />
        </span>
        <span className="text-sm font-semibold tracking-widest">FORGE</span>
      </span>
      <Button
        variant="ghost"
        className="px-2"
        aria-pressed={sidebarOpen}
        aria-label={sidebarOpen ? "Recolher a navegação" : "Expandir a navegação"}
        onClick={onToggleSidebar}
      >
        <IconPanel className="size-4" />
      </Button>
      <div className="ml-auto flex items-center gap-2">
        <p className="hidden text-sm text-forge-muted sm:block">Ambiente local</p>
        <Button
          variant="ghost"
          className="px-2"
          aria-label="Abrir configurações"
          onClick={onOpenSettings}
        >
          <IconUser className="size-4" />
        </Button>
        <Button
          variant="ghost"
          className="px-2"
          aria-pressed={canvasOpen}
          aria-label={canvasOpen ? "Recolher o Canvas" : "Expandir o Canvas"}
          onClick={onToggleCanvas}
        >
          <IconPanel className="size-4" />
        </Button>
      </div>
    </header>
  );
}
