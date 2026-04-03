import { NarrativePanel } from "../narrative/NarrativePanel";
import { Sidebar } from "../sidebar/Sidebar";

export function MainLayout() {
  return (
    <div className="flex flex-1 min-h-0 relative">
      <NarrativePanel />
      <Sidebar />
    </div>
  );
}
