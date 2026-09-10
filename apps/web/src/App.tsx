import { useMemo, useRef, useState, type ReactNode } from "react";

import {
  AdvisorApiError,
  createAdvisorClient,
  type CarePlan,
  type CarePlanPreviewResponse,
  type RecommendationItem,
  type RecommendationResponse,
} from "@advisor/api-client";

import {
  buildRecommendationRequest,
  initialDraft,
  type Category,
  type QuestionnaireDraft,
} from "./questionnaire";

const categories: { value: Category; label: string; description: string }[] = [
  { value: "PLANT", label: "Plant", description: "A safer green match for your space" },
  { value: "DOG", label: "Dog", description: "A breed profile that fits your routine" },
  { value: "CAT", label: "Cat", description: "A companion matched to your household" },
];

const api = createAdvisorClient();

export function App() {
  const [draft, setDraft] = useState<QuestionnaireDraft>(initialDraft);
  const [progress, setProgress] = useState({ percent: 0, message: "Ready when you are" });
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [preview, setPreview] = useState<CarePlanPreviewResponse | null>(null);
  const [savedPlan, setSavedPlan] = useState<CarePlan | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionId = useMemo(() => crypto.randomUUID(), []);

  const update = <K extends keyof QuestionnaireDraft>(key: K, value: QuestionnaireDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  async function requestRecommendations() {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setResult(null);
    setPreview(null);
    setSavedPlan(null);
    setProgress({ percent: 0, message: "Starting your recommendation" });
    setIsLoading(true);

    try {
      await api.streamRecommendations(
        buildRecommendationRequest(draft, sessionId),
        (event) => {
          if (event.event === "progress") {
            setProgress({ percent: event.data.percent, message: event.data.message });
          } else if (event.event === "completed") {
            setResult(event.data);
            setProgress({ percent: 100, message: "Your matches are ready" });
          } else {
            setError(event.data.message);
          }
        },
        { signal: controller.signal },
      );
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(formatError(reason));
      }
    } finally {
      if (abortRef.current === controller) {
        setIsLoading(false);
      }
    }
  }

  async function previewCarePlan(item: RecommendationItem) {
    setError(null);
    setSavedPlan(null);
    try {
      setPreview(
        await api.previewCarePlan({
          category: draft.category,
          item_name: item.name,
          recommendation_id: item.recommendation_id,
          session_id: sessionId,
          start_date: new Date().toISOString().slice(0, 10),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        }),
      );
    } catch (reason) {
      setError(formatError(reason));
    }
  }

  async function saveCarePlan() {
    if (!preview) return;
    setError(null);
    try {
      setSavedPlan(await api.createCarePlan(preview.preview_id));
    } catch (reason) {
      setError(formatError(reason));
    }
  }

  return (
    <main>
      <header className="hero">
        <p className="eyebrow">Homegrown guidance</p>
        <h1>Find the right life for your home.</h1>
        <p className="hero-copy">
          Thoughtful plant and pet matches, grounded in safety, lifestyle, and local context.
        </p>
      </header>

      <section className="workspace" aria-label="Recommendation advisor">
        <form
          className="questionnaire"
          onSubmit={(event) => {
            event.preventDefault();
            void requestRecommendations();
          }}
        >
          <fieldset className="category-picker">
            <legend>What are you hoping to welcome home?</legend>
            <div className="category-grid">
              {categories.map((category) => (
                <label
                  className={`category-card ${draft.category === category.value ? "selected" : ""}`}
                  key={category.value}
                >
                  <input
                    checked={draft.category === category.value}
                    name="category"
                    onChange={() => update("category", category.value)}
                    type="radio"
                    value={category.value}
                  />
                  <span className="category-name">{category.label}</span>
                  <span>{category.description}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="field-grid">
            <Field label="ZIP code">
              <input
                autoComplete="postal-code"
                inputMode="numeric"
                maxLength={10}
                onChange={(event) => update("zipCode", event.target.value)}
                required
                value={draft.zipCode}
              />
            </Field>
            <Field label="State">
              <input
                autoComplete="address-level1"
                maxLength={2}
                onChange={(event) => update("stateCode", event.target.value.toUpperCase())}
                value={draft.stateCode}
              />
            </Field>
            <Field label="Monthly budget">
              <input
                min="0"
                onChange={(event) => update("monthlyBudget", event.target.valueAsNumber)}
                required
                type="number"
                value={draft.monthlyBudget}
              />
            </Field>
            <SelectField
              label="Your experience"
              onChange={(value) => update("experience", value as QuestionnaireDraft["experience"])}
              options={["BEGINNER", "INTERMEDIATE", "EXPERT"]}
              value={draft.experience}
            />
          </div>

          {draft.category === "PLANT" ? (
            <PlantFields draft={draft} update={update} />
          ) : (
            <PetFields draft={draft} update={update} />
          )}

          <label className="check-field">
            <input
              checked={draft.childrenPresent}
              onChange={(event) => update("childrenPresent", event.target.checked)}
              type="checkbox"
            />
            Children live in this home
          </label>

          <button className="primary-button" disabled={isLoading} type="submit">
            {isLoading ? "Finding thoughtful matches…" : "Find my matches"}
          </button>
        </form>

        <aside className="results" aria-live="polite">
          <div className="results-heading">
            <div>
              <p className="eyebrow">Your shortlist</p>
              <h2>{result ? `${result.recommendations.length} considered matches` : "Recommendations will appear here"}</h2>
            </div>
            {result && <span className={`status ${result.validation_status.toLowerCase()}`}>{result.validation_status}</span>}
          </div>

          {(isLoading || progress.percent > 0) && !error && (
            <div className="progress-panel">
              <div className="progress-copy"><span>{progress.message}</span><strong>{progress.percent}%</strong></div>
              <progress max="100" value={progress.percent}>{progress.percent}%</progress>
            </div>
          )}

          {error && <div className="error-panel" role="alert">{error}</div>}

          {!result && !isLoading && !error && (
            <div className="empty-state">
              <div className="leaf-mark">⌁</div>
              <p>Tell us about your space and routine. We’ll show why each option fits—and flag concerns clearly.</p>
            </div>
          )}

          <div className="recommendation-list">
            {result?.warnings?.map((warning) => <p className="warning" key={warning}>{warning}</p>)}
            {result?.recommendations.map((item) => (
              <article className={`recommendation ${item.best_match ? "best" : ""}`} key={item.recommendation_id}>
                <div className="recommendation-title">
                  <div>
                    {item.best_match && <span className="best-label">Best match</span>}
                    <h3>{item.name}</h3>
                    {item.scientific_name && <p className="scientific">{item.scientific_name}</p>}
                  </div>
                  <span className="score">{Math.round(item.score)}%</span>
                </div>
                <p>{item.profile}</p>
                <ul>{item.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
                {item.concerns && item.concerns.length > 0 && (
                  <p className="concern"><strong>Keep in mind:</strong> {item.concerns.join(" ")}</p>
                )}
                <div className="safety-row">
                  <span>Dog: {friendly(item.safety.dog_toxicity)}</span>
                  <span>Cat: {friendly(item.safety.cat_toxicity)}</span>
                  <span>Child: {friendly(item.safety.child_toxicity)}</span>
                </div>
                <button className="secondary-button" onClick={() => void previewCarePlan(item)} type="button">
                  Preview care plan
                </button>
              </article>
            ))}
          </div>

          {preview && (
            <section className="care-plan">
              <p className="eyebrow">Review before saving</p>
              <h3>{preview.item_name} care plan</h3>
              <ol>
                {preview.tasks.map((task) => (
                  <li key={task.task_id}><strong>{task.title}</strong><span>{task.instructions} · Due {task.next_due_on}</span></li>
                ))}
              </ol>
              <button className="primary-button" disabled={Boolean(savedPlan)} onClick={() => void saveCarePlan()} type="button">
                {savedPlan ? "Care plan saved" : "Confirm and save plan"}
              </button>
            </section>
          )}
        </aside>
      </section>
    </main>
  );
}

type UpdateDraft = <K extends keyof QuestionnaireDraft>(key: K, value: QuestionnaireDraft[K]) => void;

function PlantFields({ draft, update }: { draft: QuestionnaireDraft; update: UpdateDraft }) {
  return (
    <div className="field-grid contextual-fields">
      <SelectField label="Light" onChange={(value) => update("lightLevel", value as QuestionnaireDraft["lightLevel"])} options={["LOW", "MEDIUM", "BRIGHT_INDIRECT", "DIRECT"]} value={draft.lightLevel} />
      <SelectField label="Humidity" onChange={(value) => update("humidity", value as QuestionnaireDraft["humidity"])} options={["LOW", "AVERAGE", "HIGH"]} value={draft.humidity} />
      <SelectField label="Available space" onChange={(value) => update("availableSpace", value as QuestionnaireDraft["availableSpace"])} options={["SMALL", "MEDIUM", "LARGE"]} value={draft.availableSpace} />
      <SelectField label="Watering time" onChange={(value) => update("wateringAvailability", value as QuestionnaireDraft["wateringAvailability"])} options={["LOW", "MEDIUM", "HIGH"]} value={draft.wateringAvailability} />
      <Field label="Indoor temperature (°F)"><input max="100" min="40" onChange={(event) => update("indoorTemperatureF", event.target.valueAsNumber)} type="number" value={draft.indoorTemperatureF} /></Field>
      <SelectField label="Pets at home" onChange={(value) => update("petsPresent", value ? [value as "DOG" | "CAT"] : [])} options={["", "DOG", "CAT"]} value={draft.petsPresent[0] ?? ""} />
    </div>
  );
}

function PetFields({ draft, update }: { draft: QuestionnaireDraft; update: UpdateDraft }) {
  return (
    <div className="field-grid contextual-fields">
      <SelectField label="Housing" onChange={(value) => update("housingType", value as QuestionnaireDraft["housingType"])} options={["APARTMENT", "CONDO", "HOUSE"]} value={draft.housingType} />
      <SelectField label="Home size" onChange={(value) => update("homeSize", value as QuestionnaireDraft["homeSize"])} options={["SMALL", "MEDIUM", "LARGE"]} value={draft.homeSize} />
      <SelectField label="Activity level" onChange={(value) => update("activityLevel", value as QuestionnaireDraft["activityLevel"])} options={["LOW", "MEDIUM", "HIGH"]} value={draft.activityLevel} />
      <SelectField label="Grooming tolerance" onChange={(value) => update("groomingTolerance", value as QuestionnaireDraft["groomingTolerance"])} options={["LOW", "MEDIUM", "HIGH"]} value={draft.groomingTolerance} />
      <Field label="Hours alone daily"><input max="24" min="0" onChange={(event) => update("hoursAlone", event.target.valueAsNumber)} type="number" value={draft.hoursAlone} /></Field>
      <SelectField label="Existing pets" onChange={(value) => update("existingPets", value ? [value as "DOG" | "CAT"] : [])} options={["", "DOG", "CAT"]} value={draft.existingPets[0] ?? ""} />
      <SelectField label="Outdoor space" onChange={(value) => update("outdoorSpace", value as QuestionnaireDraft["outdoorSpace"])} options={["NONE", "BALCONY", "YARD"]} value={draft.outdoorSpace} />
      <label className="check-field compact"><input checked={draft.rentalAllowsPets} onChange={(event) => update("rentalAllowsPets", event.target.checked)} type="checkbox" />Housing allows pets</label>
      {draft.category === "CAT" && (
        <SelectField label="Affection style" onChange={(value) => update("affectionPreference", value as QuestionnaireDraft["affectionPreference"])} options={["INDEPENDENT", "BALANCED", "AFFECTIONATE"]} value={draft.affectionPreference} />
      )}
    </div>
  );
}

function Field({ children, label }: { children: ReactNode; label: string }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

function SelectField({ label, onChange, options, value }: { label: string; onChange: (value: string) => void; options: string[]; value: string }) {
  return (
    <Field label={label}>
      <select onChange={(event) => onChange(event.target.value)} value={value}>
        {options.map((option) => <option key={option || "none"} value={option}>{option ? friendly(option) : "None"}</option>)}
      </select>
    </Field>
  );
}

function friendly(value: string) {
  return value.toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function formatError(reason: unknown) {
  if (reason instanceof AdvisorApiError) {
    return reason.requestId ? `${reason.message} Request ID: ${reason.requestId}` : reason.message;
  }
  return reason instanceof Error ? reason.message : "Something went wrong. Please try again.";
}
