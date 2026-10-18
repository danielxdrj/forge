import { useState } from "react";
import Button from "../components/Button.jsx";
import EmptyState from "../components/EmptyState.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Tabs from "../components/Tabs.jsx";

const tabs = [
  { id: "automacoes", label: "Automações" },
  { id: "provedores", label: "Provedores" },
  { id: "agentes", label: "Agentes" },
  { id: "historico", label: "Histórico" },
];

const copy = {
  automacoes: "As automações aparecem aqui quando a integração existir.",
  provedores: "Os provedores de modelo aparecem aqui quando forem configurados.",
  agentes: "Os fluxos de agentes aparecem aqui quando existirem.",
  historico: "O histórico de execução aparece aqui quando houver execuções reais.",
};

export default function AutomationsPage() {
  const [tab, setTab] = useState("automacoes");

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Automações & LLMs"
        description="Acompanhe automações, provedores e fluxos de agentes. Nesta etapa a tela não chama modelo nenhum."
        action={
          <Button disabled title="Depende da integração com o backend">
            Nova automação
          </Button>
        }
      />
      <section className="rounded-xl border border-forge-line bg-forge-panel p-4">
        <Tabs label="Automações e modelos" tabs={tabs} active={tab} onChange={setTab} />
        <div
          role="tabpanel"
          id={`${tab}-panel`}
          aria-labelledby={`${tab}-tab`}
          className="pt-4"
        >
          <EmptyState>{copy[tab]}</EmptyState>
          <p className="mt-3 text-sm text-forge-muted">
            As ações desta seção dependem da integração com o backend.
          </p>
        </div>
      </section>
    </div>
  );
}
