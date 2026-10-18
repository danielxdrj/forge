import { useState } from "react";
import EmptyState from "./EmptyState.jsx";
import Tabs from "./Tabs.jsx";
import { IconClose } from "./icons.jsx";

const tabs = [
  { id: "mapa", label: "Mapa" },
  { id: "arquitetura", label: "Arquitetura" },
  { id: "documentacao", label: "Documentação" },
];

const copy = {
  mapa: "O mapa da investigação aparece aqui quando houver uma investigação selecionada.",
  arquitetura: "A visão de arquitetura aparece aqui quando houver dados da investigação.",
  documentacao: "A documentação ligada à investigação aparece aqui quando estiver disponível.",
};

export default function CanvasPanel({ onClose }) {
  const [tab, setTab] = useState("mapa");

  return (
    <aside
      aria-label="Canvas"
      className="flex w-full shrink-0 flex-col border-forge-line bg-forge-panel lg:w-80 lg:border-l"
    >
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="text-sm font-semibold">Canvas</h2>
        <button
          type="button"
          className="rounded-md p-1 text-forge-muted hover:bg-forge-raised"
          aria-label="Recolher o Canvas"
          onClick={onClose}
        >
          <IconClose className="size-4" />
        </button>
      </div>
      <div className="px-3">
        <Tabs label="Canvas" tabs={tabs} active={tab} onChange={setTab} />
      </div>
      <div
        role="tabpanel"
        id={`${tab}-panel`}
        aria-labelledby={`${tab}-tab`}
        className="p-4"
      >
        <EmptyState>{copy[tab]}</EmptyState>
      </div>
    </aside>
  );
}
