import { useState } from "react";
import Button from "../components/Button.jsx";
import EmptyState from "../components/EmptyState.jsx";
import PageHeader from "../components/PageHeader.jsx";
import TextField from "../components/TextField.jsx";

const connectionTypes = [
  { id: "database", label: "Banco de dados" },
  { id: "ftp", label: "FTP/SFTP" },
  { id: "repository", label: "Repositório Git" },
  { id: "portainer", label: "Portainer" },
];

const connections = [];

function required(value) {
  return value.trim() ? "" : "Preencha este campo.";
}

export default function ConnectionsPage() {
  const [name, setName] = useState("");
  const [type, setType] = useState("database");
  const [destination, setDestination] = useState("");
  const [secretReference, setSecretReference] = useState("");
  const [errors, setErrors] = useState({});
  const [notice, setNotice] = useState("");

  function submit(event) {
    event.preventDefault();
    const nextErrors = {
      name: required(name),
      destination: required(destination),
      secretReference: required(secretReference),
    };
    setErrors(nextErrors);
    if (Object.values(nextErrors).some(Boolean)) {
      setNotice("");
      return;
    }
    setNotice("O cadastro ainda depende da integração com o backend. Nenhuma conexão foi gravada.");
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Conexões"
        description="Tipos previstos para fontes autorizadas. Nenhum deles está configurado nem consultado nesta tela."
      />
      <section aria-label="Tipos de conexão" className="grid gap-3 sm:grid-cols-2">
        {connectionTypes.map((item) => (
          <article key={item.id} className="rounded-xl border border-forge-line bg-forge-panel p-4">
            <h2 className="text-sm font-semibold">{item.label}</h2>
            <p className="mt-1 text-sm text-forge-muted">Tipo disponível. Nenhuma conexão deste tipo foi cadastrada.</p>
          </article>
        ))}
      </section>
      <section className="grid gap-4 rounded-xl border border-forge-line bg-forge-panel p-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <form className="grid gap-3" onSubmit={submit}>
          <h2 className="text-base font-semibold">Cadastro</h2>
          <TextField
            id="connection-name"
            label="Nome"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          {errors.name ? <p className="text-sm text-forge-amber">{errors.name}</p> : null}
          <div>
            <label htmlFor="connection-type" className="mb-1 block text-sm text-forge-muted">
              Tipo
            </label>
            <select
              id="connection-type"
              value={type}
              onChange={(event) => setType(event.target.value)}
              className="w-full rounded-lg border border-forge-line bg-forge-bg px-3 py-2 text-sm"
            >
              {connectionTypes.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <TextField
            id="connection-destination"
            label="Destino"
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
          />
          {errors.destination ? <p className="text-sm text-forge-amber">{errors.destination}</p> : null}
          <TextField
            id="connection-secret-reference"
            label="Referência do segredo"
            value={secretReference}
            onChange={(event) => setSecretReference(event.target.value)}
            hint="Somente a referência. O valor do segredo não entra neste formulário."
          />
          {errors.secretReference ? (
            <p className="text-sm text-forge-amber">{errors.secretReference}</p>
          ) : null}
          {notice ? (
            <p role="status" className="text-sm text-forge-amber">
              {notice}
            </p>
          ) : null}
          <Button type="submit" className="w-fit">
            Cadastrar
          </Button>
        </form>
        <div>
          <h2 className="mb-3 text-base font-semibold">Cadastradas</h2>
          {connections.length === 0 ? (
            <EmptyState>Nenhuma conexão cadastrada.</EmptyState>
          ) : null}
        </div>
      </section>
    </div>
  );
}
