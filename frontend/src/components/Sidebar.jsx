import {
  IconAutomation,
  IconConnection,
  IconInvestigation,
  IconLog,
  IconMark,
  IconSettings,
} from "./icons.jsx";

const items = [
  { id: "investigacao", label: "Investigação", icon: IconInvestigation },
  { id: "automacoes", label: "Automações & LLMs", icon: IconAutomation },
  { id: "log", label: "Log Local", icon: IconLog },
  { id: "conexoes", label: "Conexões", icon: IconConnection },
  { id: "configuracoes", label: "Configurações", icon: IconSettings },
];

export default function Sidebar({ page, onNavigate }) {
  return (
    <nav
      aria-label="Seções"
      className="flex w-60 shrink-0 flex-col border-r border-forge-line bg-forge-panel"
    >
      <ul className="flex flex-1 flex-col gap-1 px-2 pt-3">
        {items.map((item) => {
          const active = page === item.id;
          const Icon = item.icon;
          return (
            <li key={item.id}>
              <button
                type="button"
                aria-current={active ? "page" : undefined}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm ${
                  active
                    ? "bg-forge-raised text-forge-blue"
                    : "text-forge-muted hover:bg-forge-raised hover:text-forge-text"
                }`}
                onClick={() => onNavigate(item.id)}
              >
                <Icon className="size-5 shrink-0" />
                <span>{item.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="m-3 rounded-xl border border-forge-line bg-forge-bg p-3">
        <div className="mb-2 flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-md bg-forge-blue text-white">
            <IconMark className="size-3.5" />
          </span>
          <p className="text-sm font-medium">Forge</p>
        </div>
        <p className="text-xs text-forge-muted">
          Copiloto local para investigação, análise e correção que depende de aprovação.
        </p>
      </div>
    </nav>
  );
}
