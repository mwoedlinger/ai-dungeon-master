import { useState } from "react";
import { searchCompendium } from "../../api/rest";

const CATEGORIES = [
  "monsters",
  "spells",
  "equipment",
  "magic-items",
  "classes",
  "races",
  "conditions",
  "skills",
];

export function CompendiumTab() {
  const [category, setCategory] = useState("monsters");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSearch() {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await searchCompendium(category, query.trim());
      setResults(data);
    } catch (e) {
      setResults({ error: String(e) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      {/* Category select */}
      <select
        value={category}
        onChange={(e) => setCategory(e.target.value)}
        className="w-full px-2.5 py-1.5 text-[11px] rounded-md
          bg-bg/60 border border-border-subtle
          text-text-primary font-display tracking-wider
          focus:outline-none focus:border-accent"
      >
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>

      {/* Search input */}
      <div className="flex gap-1.5">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder="Search the compendium..."
          className="flex-1 px-2.5 py-1.5 text-xs rounded-md
            bg-bg/60 border border-border-subtle
            text-text-primary placeholder:text-text-mechanical/40
            focus:outline-none focus:border-accent"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="px-3 py-1.5 text-[10px] rounded-md btn-primary font-display tracking-wider"
        >
          {loading ? "..." : "Search"}
        </button>
      </div>

      {/* Results */}
      {results && (
        <div className="card p-3">
          {Array.isArray(results) ? (
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {(results as { name: string; index: string }[])
                .slice(0, 30)
                .map((r, i) => (
                  <div
                    key={i}
                    className="text-xs cursor-pointer hover:text-accent transition-colors py-0.5
                      border-b border-border-subtle/30 last:border-0"
                    onClick={() => {
                      setQuery(r.index || r.name);
                      handleSearch();
                    }}
                  >
                    <span className="text-accent">{r.name}</span>
                    <span className="text-text-mechanical/40 ml-1 text-[10px] font-mono">
                      {r.index}
                    </span>
                  </div>
                ))}
            </div>
          ) : (
            <pre className="text-[10px] text-text-secondary/70 whitespace-pre-wrap break-words max-h-80 overflow-y-auto font-mono leading-relaxed">
              {JSON.stringify(results, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
