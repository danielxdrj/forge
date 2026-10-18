import { useMemo, useState } from "react";
import Button from "../components/Button.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Modal from "../components/Modal.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Pagination from "../components/Pagination.jsx";
import Tabs from "../components/Tabs.jsx";
import TextField from "../components/TextField.jsx";
import { IconPlus, IconSearch } from "../components/icons.jsx";
import { paginate } from "../lib/pagination.js";

const investigations = [];
const pageSize = 20;

const detailTabs = [
  { id: "chat", label: "Chat" },
  { id: "evidencias", label: "Evidências" },
  { id: "resumo", label: "Resumo" },
  { id: "sugestao", label: "Sugestão" },
];

function validateTitle(value) {
  const title = value.trim();
  if (!title) return "Informe um título.";
  if (title.length > 200) return "O título pode ter no máximo 200 caracteres.";
  return "";
}

export default function InvestigationPage({ detailTab, onDetailTab }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [titleError, setTitleError] = useState("");
  const [createNotice, setCreateNotice] = useState("");
  const [message, setMessage] = useState("");
  const [messageNotice, setMessageNotice] = useState("");

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return investigations;
    return investigations.filter((item) => {
      const id = String(item.id ?? "");
      const name = String(item.title ?? "").toLowerCase();
      return id.includes(term) || name.includes(term);
    });
  }, [query]);

  const listing = paginate(filtered, page, pageSize);

  function openModal() {
    setTitle("");
    setTitleError("");
    setCreateNotice("");
    setModalOpen(true);
  }

  function submitInvestigation(event) {
    event.preventDefault();
    const error = validateTitle(title);
    setTitleError(error);
    if (error) {
      setCreateNotice("");
      return;
    }
    setCreateNotice("A criação ainda depende da integração com o backend. Nenhum registro foi criado.");
  }

  function submitMessage(event) {
    event.preventDefault();
    if (!message.trim()) {
      setMessageNotice("Escreva a mensagem antes de enviar.");
      return;
    }
    setMessageNotice("A conversa ainda depende da integração com o backend. Nenhuma resposta foi gerada.");
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Investigações"
        description="Crie e consulte investigações quando a API estiver ligada. Esta tela ainda não grava nem lista registros."
        action={
          <Button onClick={openModal}>
            <IconPlus className="size-4" />
            Nova investigação
          </Button>
        }
      />

      <div className="grid min-h-[32rem] gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
        <section aria-label="Lista de investigações" className="flex flex-col gap-3 rounded-xl border border-forge-line bg-forge-panel p-4">
          <div className="relative">
            <IconSearch className="pointer-events-none absolute top-2.5 left-3 size-4 text-forge-muted" />
            <label htmlFor="investigation-search" className="sr-only">
              Buscar por título ou identificador
            </label>
            <input
              id="investigation-search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder="Buscar por título ou identificador"
              className="w-full rounded-lg border border-forge-line bg-forge-bg py-2 pr-3 pl-9 text-sm"
            />
          </div>
          <div>
            <label htmlFor="investigation-filter" className="mb-1 block text-xs text-forge-muted">
              Filtros
            </label>
            <select
              id="investigation-filter"
              disabled
              className="w-full rounded-lg border border-forge-line bg-forge-bg px-3 py-2 text-sm"
              defaultValue=""
            >
              <option value="">Nenhum filtro definido</option>
            </select>
          </div>
          {listing.total === 0 ? (
            <EmptyState>Suas investigações aparecerão aqui quando estiverem disponíveis.</EmptyState>
          ) : null}
          <Pagination
            page={listing.page}
            totalPages={listing.totalPages}
            from={listing.from}
            to={listing.to}
            total={listing.total}
            onPageChange={setPage}
          />
        </section>

        <section aria-label="Detalhe da investigação" className="flex min-w-0 flex-col rounded-xl border border-forge-line bg-forge-panel">
          <div className="border-b border-forge-line px-4 py-4">
            <h2 className="text-base font-semibold">Detalhe</h2>
            <p className="mt-1 text-sm text-forge-muted">
              Selecione uma investigação para consultar seus detalhes e evidências.
            </p>
          </div>
          <div className="px-2">
            <Tabs
              label="Detalhe da investigação"
              tabs={detailTabs}
              active={detailTab}
              onChange={onDetailTab}
            />
          </div>
          <div
            role="tabpanel"
            id={`${detailTab}-panel`}
            aria-labelledby={`${detailTab}-tab`}
            className="flex flex-1 flex-col gap-4 p-4"
          >
            {detailTab === "chat" ? (
              <>
                <p className="rounded-lg border border-forge-line bg-forge-bg px-3 py-3 text-sm text-forge-muted">
                  A conversa aparece aqui depois que uma investigação existir e a tela estiver ligada à API. Nenhuma resposta é gerada nesta etapa.
                </p>
                <form className="mt-auto grid gap-2" onSubmit={submitMessage}>
                  <TextField
                    id="investigation-message"
                    label="Mensagem"
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    placeholder="Escreva uma mensagem"
                  />
                  <Button type="submit" className="w-fit">
                    Enviar
                  </Button>
                  {messageNotice ? (
                    <p role="status" className="text-sm text-forge-amber">
                      {messageNotice}
                    </p>
                  ) : null}
                </form>
              </>
            ) : null}
            {detailTab === "evidencias" ? (
              <EmptyState>As evidências da investigação selecionada aparecerão aqui.</EmptyState>
            ) : null}
            {detailTab === "resumo" ? (
              <EmptyState>O resumo aparece aqui quando houver uma investigação selecionada.</EmptyState>
            ) : null}
            {detailTab === "sugestao" ? (
              <EmptyState>
                A sugestão de correção aparece aqui depois da análise. Esta tela não aplica a correção.
              </EmptyState>
            ) : null}
          </div>
        </section>
      </div>

      {modalOpen ? (
        <Modal title="Nova investigação" onClose={() => setModalOpen(false)}>
          <form className="grid gap-3" onSubmit={submitInvestigation}>
            <TextField
              id="new-investigation-title"
              label="Título"
              value={title}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
              hint="Até 200 caracteres, sem ficar em branco."
            />
            {titleError ? (
              <p role="alert" className="text-sm text-forge-amber">
                {titleError}
              </p>
            ) : null}
            {createNotice ? (
              <p role="status" className="text-sm text-forge-amber">
                {createNotice}
              </p>
            ) : null}
            <Button type="submit" className="w-fit">
              Criar
            </Button>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
