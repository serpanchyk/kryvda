import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  chatgptPrompt,
  mutablePayload,
  parseAnnotationPayload,
} from "./json-record.js";
import { codePointSpan, spanText } from "./spans.js";
import "./style.css";

const labels = {
  selection: "Відбір прикладу",
  facets: "Особливості прикладу",
  reason: "Чому обрано цей пост",
  entities: "Сутності",
  stances: "Ставлення",
  claims: "Твердження",
  rhetorical_features: "Риторичні ознаки",
  surface_form: "Згадка у тексті",
  canonical_name: "Канонічна назва",
  registry_entity_id: "Запис довідника",
  entity_type: "Тип сутності",
  registry_status: "Статус у довіднику",
  resolution_source: "Як визначено особу",
  subject_role: "Роль у пості",
  mention_span: "Фрагмент згадки",
  evidence_spans: "Фрагменти-докази",
  evidence_span: "Фрагмент-доказ",
  entity_id: "Сутність",
  entity_ids: "Учасники твердження",
  perspective: "Хто висловлює ставлення",
  attribution: "Хто висловлює твердження",
  value: "Ставлення",
  normalized_text: "Нормалізоване твердження",
  presentation: "Форма подачі",
  epistemic_status: "Статус твердження",
  feature_type: "Риторична ознака",
  target_entity_id: "Ціль: сутність",
  target_claim_id: "Ціль: твердження",
  source_kind: "Джерело висловлювання",
  source_entity_id: "Автор: сутність",
  primary: "Основна",
  secondary: "Другорядна",
  person: "Людина",
  organization: "Організація",
  state_institution: "Державна установа",
  media_outlet: "Медіа",
  political_actor: "Політичний актор",
  candidate: "Кандидат",
  monitored: "Моніториться",
  ignored: "Ігнорується",
  unresolved: "Не визначено",
  registry: "Довідник",
  annotator_knowledge: "Визначено анотатором",
  positive: "Позитивне",
  neutral: "Нейтральне",
  negative: "Негативне",
  mixed: "Змішане",
  insufficient_context: "Недостатньо контексту",
  channel_editorial: "Голос каналу",
  named_entity: "Названий автор",
  external_unnamed: "Неназване зовнішнє джерело",
  unknown: "Невідомо",
  editorial: "Авторський текст",
  direct_quote: "Пряма цитата",
  reported: "Переказ",
  repost: "Репост",
  asserted: "Стверджено",
  alleged: "Нібито / припущено",
  denied: "Заперечено",
  hypothetical: "Гіпотетично",
  questioned: "Поставлено питання",
  derogatory_labeling: "Образливе називання",
  ridicule: "Висміювання",
  delegitimization: "Делегітимізація",
  foreign_control_accusation: "Звинувачення у зовнішньому контролі",
  corruption_accusation: "Звинувачення в корупції",
  criminality_accusation: "Звинувачення у злочині",
  grant_discrediting: "Дискредитація через гранти",
  hypocrisy_claim: "Звинувачення в лицемірстві",
  call_for_punishment: "Заклик до покарання",
};
const title = (key) => labels[key] || key;
async function api(path, method = "GET", body) {
  const response = await fetch("/api/" + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail),
    );
  return result;
}

function App() {
  const [schema, setSchema] = useState(null),
    [importSchema, setImportSchema] = useState(null),
    [state, setState] = useState({ records: {}, registry: [] });
  const [posts, setPosts] = useState([]),
    [channels, setChannels] = useState([]),
    [filters, setFilters] = useState({
      q: "",
      channel: "",
      date_from: "",
      date_to: "",
    });
  const [item, setItem] = useState(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [selected, setSelected] = useState(null);
  const [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [tab, setTab] = useState("entities"),
    [editorMode, setEditorMode] = useState("form"),
    [jsonText, setJsonText] = useState(""),
    [importPreview, setImportPreview] = useState(null),
    [savedOnly, setSavedOnly] = useState(false);
  const textRef = useRef(null),
    current = useRef(null),
    saving = useRef(false);
  current.current = item;
  const refresh = async () => setState(await api("state"));
  const search = async (before) => {
    try {
      setError("");
      const params = new URLSearchParams(
        Object.entries(filters).filter(([, v]) => v),
      );
      if (before) params.set("before", before);
      setPosts(await api("posts?" + params));
    } catch (e) {
      setError(e.message);
    }
  };
  useEffect(() => {
    api("schema")
      .then(setSchema)
      .catch((e) => setError(e.message));
    api("import-schema")
      .then(setImportSchema)
      .catch((e) => setError(e.message));
    refresh().catch((e) => setError(e.message));
    api("channels")
      .then(setChannels)
      .catch((e) => setError(e.message));
    search();
  }, []);
  useEffect(() => {
    const warn = (e) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  async function persist(status = "draft") {
    if (!current.current || saving.current) return false;
    saving.current = true;
    setBusy(true);
    const snapshot = current.current;
    try {
      const updated = await api(
        "records/" + snapshot.record.source.post_revision_id,
        "PUT",
        { ...snapshot, status },
      );
      setItem(updated);
      setDirty(false);
      setNotice(
        status === "completed"
          ? "Завершено та додано до golden_v0"
          : "Чернетку збережено",
      );
      await refresh();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    if (!dirty || importPreview) return;
    const timer = setTimeout(() => persist(), 1000);
    return () => clearTimeout(timer);
  }, [item, dirty, importPreview]);
  const open = async (source) => {
    if (saving.current) return;
    if (dirty && !importPreview && !(await persist())) return;
    try {
      setItem(await api("start/" + source.post_revision_id, "POST"));
      setSelected(null);
      setEditorMode("form");
      setJsonText("");
      setImportPreview(null);
      setNotice("");
      setError("");
      setDirty(false);
    } catch (e) {
      setError(e.message);
    }
  };
  function update(record) {
    setItem({ ...item, record });
    setDirty(true);
    setNotice("Зберігаємо…");
  }
  async function copyChatgptPrompt() {
    try {
      await navigator.clipboard.writeText(
        chatgptPrompt(importSchema, record.source, mutablePayload(record)),
      );
      setNotice("Пакет для ChatGPT скопійовано");
      setError("");
    } catch {
      setError("Не вдалося скопіювати пакет. Дозвольте доступ до буфера обміну.");
    }
  }
  async function previewImport() {
    let imported;
    try {
      imported = parseAnnotationPayload(jsonText);
    } catch (e) {
      setError(`Не вдалося прочитати JSON: ${e.message}`);
      return;
    }
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    try {
      const updated = await api(
        "records/" + record.source.post_revision_id + "/import-preview",
        "POST",
        { version: item.version, payload: imported },
      );
      setItem({ ...item, record: updated.record });
      setDirty(false);
      setImportPreview(updated.candidates);
      setEditorMode("form");
      setNotice("JSON перевірено: перегляньте результат перед збереженням");
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  async function confirmImport() {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    try {
      const updated = await api(
        "records/" + record.source.post_revision_id + "/complete-import",
        "POST",
        { version: item.version, payload: mutablePayload(record) },
      );
      setItem(updated);
      setDirty(false);
      setImportPreview(null);
      setNotice("Перевірену анотацію додано до golden_v0");
      setError("");
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  function capture() {
    const selection = window.getSelection();
    if (!selection?.rangeCount || selection.isCollapsed) return;
    const range = selection.getRangeAt(0),
      root = textRef.current;
    if (
      !root.contains(range.startContainer) ||
      !root.contains(range.endContainer)
    )
      return;
    const prefix = range.cloneRange();
    prefix.selectNodeContents(root);
    prefix.setEnd(range.startContainer, range.startOffset);
    const start = prefix.toString().length;
    setSelected(
      codePointSpan(
        item.record.source.text,
        start,
        start + range.toString().length,
      ),
    );
  }
  function resolve(s) {
    return s.$ref ? schema.$defs[s.$ref.split("/").pop()] : s;
  }
  function blank(s) {
    s = resolve(s);
    if (s.enum) return s.enum[0];
    if (s.type === "array") return [];
    if (s.type === "object")
      return Object.fromEntries(
        (s.required || []).map((k) => [k, blank(s.properties[k])]),
      );
    if (s.type === "boolean") return false;
    if (s.type === "integer") return 0;
    if (Array.isArray(s.type)) return null;
    return "";
  }
  const record = item?.record,
    entities = record?.annotations.entities || [],
    claims = record?.annotations.claims || [];
  function field(s, value, onChange, key, path = "") {
    s = resolve(s);
    if (
      [
        "registry_entity_id",
        "canonical_name",
        "resolution_source",
        "registry_status",
      ].includes(key)
    )
      return null;
    if (key === "id") return <small key={path}>ID: {value}</small>;
    if (s.properties?.start) {
      return (
        <div className="span" key={path}>
          <small>{title(key)}</small>
          <blockquote>
            {value && value.end > value.start
              ? spanText(record.source.text, value)
              : "Виділіть фразу в пості"}
          </blockquote>
          <button
            disabled={!selected}
            onClick={() => onChange({ ...selected })}
          >
            Використати виділення
          </button>
        </div>
      );
    }
    if (s.type === "object")
      return (
        <div className="fields" key={path}>
          {Object.entries(s.properties).map(([k, child]) => {
            if (
              k === "source_entity_id" &&
              value?.source_kind !== "named_entity"
            )
              return null;
            return field(
              child,
              value?.[k],
              (v) => {
                const next = { ...value, [k]: v };
                if (k === "source_kind" && v !== "named_entity")
                  delete next.source_entity_id;
                onChange(next);
              },
              k,
              path + "." + k,
            );
          })}
        </div>
      );
    if (s.type === "array")
      return (
        <div key={path} className="array">
          <label>{title(key)}</label>
          {(value || []).map((v, i) => (
            <div className="array-item" key={i}>
              {field(
                s.items,
                v,
                (next) =>
                  onChange(value.map((old, n) => (n === i ? next : old))),
                key,
                path + i,
              )}
              <button
                className="remove"
                onClick={() => onChange(value.filter((_, n) => n !== i))}
              >
                Прибрати
              </button>
            </div>
          ))}
          <button onClick={() => onChange([...(value || []), blank(s.items)])}>
            + Додати
          </button>
        </div>
      );
    if (
      key.endsWith("entity_id") ||
      key === "entity_ids" ||
      key === "target_claim_id"
    ) {
      const options = key === "target_claim_id" ? claims : entities;
      return (
        <label key={path}>
          {title(key)}
          <select
            value={value || ""}
            onChange={(e) => onChange(e.target.value)}
          >
            <option value="">Оберіть…</option>
            {options.map((e) => (
              <option key={e.id} value={e.id}>
                {e.surface_form || e.normalized_text} · {e.id}
              </option>
            ))}
          </select>
        </label>
      );
    }
    if (s.enum)
      return (
        <label key={path}>
          {title(key)}
          <select
            value={value || s.enum[0]}
            onChange={(e) => onChange(e.target.value)}
          >
            {s.enum.map((v) => (
              <option key={v} value={v}>
                {title(v)}
              </option>
            ))}
          </select>
        </label>
      );
    if (s.type === "boolean")
      return (
        <label key={path} className="check">
          <input
            type="checkbox"
            checked={!!value}
            onChange={(e) => onChange(e.target.checked)}
          />
          {title(key)}
        </label>
      );
    return (
      <label key={path}>
        {title(key)}
        <textarea
          rows={key === "normalized_text" ? 3 : 2}
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    );
  }
  function changeGroup(list) {
    update({ ...record, annotations: { ...record.annotations, [tab]: list } });
  }
  function removeEntry(index) {
    const entry = record.annotations[tab][index];
    const dependents = Object.fromEntries(
      Object.entries(record.annotations).filter(([key]) => key !== tab),
    );
    if (
      entry.id &&
      JSON.stringify(dependents).includes(JSON.stringify(entry.id))
    ) {
      setError(
        "Спочатку приберіть посилання на цей запис у ставленні, твердженнях або риторичних ознаках.",
      );
      return;
    }
    changeGroup(record.annotations[tab].filter((_, i) => i !== index));
  }
  function add() {
    const s =
        schema.$defs[
          {
            entities: "entity",
            stances: "stance",
            claims: "claim",
            rhetorical_features: "rhetorical_feature",
          }[tab]
        ],
      next = blank(s);
    if (tab === "entities") {
      next.id =
        "e" + (Math.max(0, ...entities.map((e) => Number(e.id.slice(1)))) + 1);
      next.resolution_source = "unresolved";
      next.registry_status = "candidate";
      if (selected) {
        next.mention_span = selected;
        next.surface_form = spanText(record.source.text, selected);
      }
    }
    if (tab === "claims")
      next.id =
        "c" + (Math.max(0, ...claims.map((e) => Number(e.id.slice(1)))) + 1);
    if (selected) {
      if ("evidence_spans" in next) next.evidence_spans = [selected];
      if ("evidence_span" in next) next.evidence_span = selected;
    }
    changeGroup([...record.annotations[tab], next]);
  }
  async function linkEntity(index, id) {
    const entry = state.registry.find((e) => e.id === id);
    const list = [...entities];
    list[index] = {
      ...list[index],
      registry_entity_id: entry?.id || null,
      canonical_name: entry?.canonical_name || null,
      registry_status: entry?.status || "candidate",
      resolution_source: entry ? "registry" : "unresolved",
    };
    changeGroup(list);
  }
  async function createEntity(index) {
    const entity = entities[index];
    const name = window.prompt(
      "Канонічна назва для локального довідника",
      entity.surface_form,
    );
    if (!name) return;
    try {
      const entry = await api("registry", "POST", {
        ...entity,
        canonical_name: name,
      });
      setState((s) => ({ ...s, registry: [...s.registry, entry] }));
      const list = [...entities];
      list[index] = {
        ...entity,
        registry_entity_id: entry.id,
        canonical_name: entry.canonical_name,
        registry_status: "candidate",
        resolution_source: "annotator_knowledge",
      };
      changeGroup(list);
    } catch (e) {
      setError(e.message);
    }
  }
  const queue = savedOnly
    ? Object.values(state.records).map((i) => i.record.source)
    : posts;
  return (
    <>
      <header>
        <div>
          <span className="brand">G</span>
          <strong>Golden studio</strong>
          <span className="badge">Пілот · v0</span>
        </div>
        <span>
          {
            Object.values(state.records).filter((i) => i.status === "completed")
              .length
          }{" "}
          завершено / ~100
        </span>
      </header>
      {error && (
        <div role="alert" className="error">
          {error}
          <button onClick={() => setError("")}>Закрити</button>
        </div>
      )}
      <main>
        <aside>
          <h2>Пости для розмітки</h2>
          <p className="muted">Знайдіть приклад і додайте його до пілота.</p>
          <input
            placeholder="Ключове слово або згадка"
            value={filters.q}
            onChange={(e) => setFilters({ ...filters, q: e.target.value })}
          />
          <select
            value={filters.channel}
            onChange={(e) =>
              setFilters({ ...filters, channel: e.target.value })
            }
          >
            <option value="">Усі канали</option>
            {channels.map((c) => (
              <option value={c.id} key={c.id}>
                {c.title}
              </option>
            ))}
          </select>
          <label>
            Від
            <input
              type="date"
              value={filters.date_from}
              onChange={(e) =>
                setFilters({ ...filters, date_from: e.target.value })
              }
            />
          </label>
          <label>
            До
            <input
              type="date"
              value={filters.date_to}
              onChange={(e) =>
                setFilters({ ...filters, date_to: e.target.value })
              }
            />
          </label>
          <button
            className="primary"
            onClick={() => {
              setSavedOnly(false);
              search();
            }}
          >
            Знайти пости
          </button>
          <button onClick={() => setSavedOnly(!savedOnly)}>
            {savedOnly ? "Показати пошук" : "Мої чернетки й готові"}
          </button>
          <div className="queue">
            {queue.map((p) => (
              <button
                disabled={busy}
                className={
                  "post " +
                  (record?.source.post_revision_id === p.post_revision_id
                    ? "active"
                    : "")
                }
                key={p.post_revision_id}
                onClick={() => open(p)}
              >
                <small>
                  @{p.channel_reference} ·{" "}
                  {state.records[p.post_revision_id]?.status === "completed"
                    ? "✓ Готово"
                    : state.records[p.post_revision_id]
                      ? "Чернетка"
                      : "Новий"}
                </small>
                <p>{p.text.slice(0, 150) || "Без тексту"}</p>
              </button>
            ))}
          </div>
          {!queue.length && (
            <p className="muted">
              Немає постів. Змініть фільтри або перевірте підключення.
            </p>
          )}
          {!savedOnly && posts.length === 30 && (
            <button onClick={() => search(posts.at(-1).post_revision_id)}>
              Наступні 30 →
            </button>
          )}
        </aside>
        {!item || !schema ? (
          <section className="welcome">
            <h1>Від тексту — до доказів.</h1>
            <p>
              Оберіть пост ліворуч. Виділіть згадку або фразу, потім додайте її
              до форми.
            </p>
            <p className="muted">Чернетки зберігаються автоматично.</p>
          </section>
        ) : (
          <>
            <section className="source">
              <div className="source-heading">
                <span className="badge">{record.example_id}</span>
                <h2>@{record.source.channel_reference}</h2>
                <small>{record.source.published_at}</small>
              </div>
              <article ref={textRef} onMouseUp={capture} onKeyUp={capture}>
                {record.source.text}
              </article>
              <div className="selection">
                <small>Виділений доказ</small>
                <p>
                  {selected
                    ? spanText(record.source.text, selected)
                    : "Виділіть фрагмент мишкою у тексті вище."}
                </p>
              </div>
              <details>
                <summary>Як розмічати</summary>
                <p>
                  Сутності — хто згаданий. Ставлення — оцінка конкретного автора
                  щодо сутності. Твердження — одна самостійна думка. Риторика —
                  окремі ознаки з доказом.
                </p>
                <p>
                  Цитата сама по собі не доводить ставлення каналу. Канонічну
                  назву обирайте з довідника або лишайте невизначеною.
                </p>
              </details>
            </section>
            <section className="editor">
              <div className="toolbar">
                <span aria-live="polite">{notice || "Готово до розмітки"}</span>
                {!importPreview && (
                  <button disabled={busy} onClick={() => persist()}>
                    Зберегти
                  </button>
                )}
              </div>
              <fieldset disabled={busy}>
                <div className="editor-mode" aria-label="Режим розмітки">
                  <button
                    className={editorMode === "form" ? "active" : ""}
                    onClick={() => setEditorMode("form")}
                    type="button"
                  >
                    Форма
                  </button>
                  <button
                    className={editorMode === "json" ? "active" : ""}
                    onClick={() => setEditorMode("json")}
                    type="button"
                  >
                    JSON
                  </button>
                </div>
                {editorMode === "json" ? (
                  <section className="json-import">
                    <h2>JSON-чернетка анотації</h2>
                    <p className="muted">
                      Скопіюйте пакет, надішліть його ChatGPT і вставте відповідь лише зі
                      змінними полями selection та annotations.
                    </p>
                    <button onClick={copyChatgptPrompt} type="button">
                      Скопіювати пакет для ChatGPT
                    </button>
                    <label>
                      JSON від ChatGPT
                      <textarea
                        aria-label="JSON від ChatGPT"
                        className="json-text"
                        placeholder={'{\n  "example_id": "golden_v0-001"\n}'}
                        rows="18"
                        value={jsonText}
                        onChange={(e) => setJsonText(e.target.value)}
                      />
                    </label>
                    <button
                      className="primary"
                      disabled={!jsonText.trim() || !importSchema}
                      onClick={previewImport}
                      type="button"
                    >
                      Перевірити та відкрити preview
                    </button>
                    <small>
                      Нічого не зберігається на цьому етапі. Спершу ви побачите результат
                      у формі та підтвердите його.
                    </small>
                  </section>
                ) : (
                  <>
                <details open>
                  <summary>Відбір прикладу</summary>
                  {field(
                    schema.properties.selection,
                    record.selection,
                    (v) => update({ ...record, selection: v }),
                    "selection",
                  )}
                </details>
                <nav>
                  {["entities", "stances", "claims", "rhetorical_features"].map(
                    (k) => (
                      <button
                        className={tab === k ? "active" : ""}
                        key={k}
                        onClick={() => setTab(k)}
                      >
                        {title(k)} <small>{record.annotations[k].length}</small>
                      </button>
                    ),
                  )}
                </nav>
                {record.annotations[tab].map((entry, index) => (
                  <div className="card" key={entry.id || index}>
                    <h3>
                      {entry.surface_form ||
                        entry.normalized_text ||
                        `${title(tab)} ${index + 1}`}
                    </h3>
                    {field(
                      schema.$defs[
                        {
                          entities: "entity",
                          stances: "stance",
                          claims: "claim",
                          rhetorical_features: "rhetorical_feature",
                        }[tab]
                      ],
                      entry,
                      (v) =>
                        changeGroup(
                          record.annotations[tab].map((old, i) =>
                            i === index ? v : old,
                          ),
                        ),
                      tab,
                    )}
                    {tab === "entities" && importPreview && (
                      <label>
                        Канонічна назва
                        <textarea
                          rows="2"
                          value={entry.canonical_name || ""}
                          onChange={(event) =>
                            changeGroup(
                              record.annotations.entities.map((old, i) =>
                                i === index
                                  ? { ...old, canonical_name: event.target.value || null }
                                  : old,
                              ),
                            )
                          }
                        />
                        <small>
                          Порожнє значення лишає згадку невизначеною. Після підтвердження
                          нова назва стане candidate у довіднику.
                        </small>
                      </label>
                    )}
                    {tab === "entities" && !importPreview && (
                      <div className="registry">
                        <label>
                          Канонічна сутність
                          <select
                            value={entry.registry_entity_id || ""}
                            onChange={(e) => linkEntity(index, e.target.value)}
                          >
                            <option value="">Не визначено</option>
                            {state.registry.map((e) => (
                              <option key={e.id} value={e.id}>
                                {e.canonical_name} · {e.aliases.join(", ")}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button onClick={() => createEntity(index)}>
                          + Створити в довіднику
                        </button>
                      </div>
                    )}
                    <button
                      className="remove"
                      onClick={() => removeEntry(index)}
                    >
                      Видалити запис
                    </button>
                  </div>
                ))}
                <button className="add" onClick={add}>
                  + Додати: {title(tab).toLowerCase()}
                </button>
                  </>
                )}
              </fieldset>
              {editorMode === "form" && (
                <footer>
                  {importPreview ? (
                    <>
                      <div className="preview-notice">
                        Preview: не збережено. Після підтвердження буде додано{" "}
                        {importPreview.length} candidate-сутностей.
                      </div>
                      <button className="primary" disabled={busy} onClick={confirmImport}>
                        Підтвердити та зберегти
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={async () => {
                          if (await persist("completed")) {
                            const next = queue.find(
                              (p) =>
                                p.post_revision_id !== record.source.post_revision_id &&
                                !state.records[p.post_revision_id],
                            );
                            if (next) await open(next);
                          }
                        }}
                      >
                        Завершити й перейти далі →
                      </button>
                      <small>Перевіряємо форму та зберігаємо в golden_v0</small>
                    </>
                  )}
                </footer>
              )}
            </section>
          </>
        )}
      </main>
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
