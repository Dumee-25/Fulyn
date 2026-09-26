import { Badge } from "@/components/ui/badge";
import type { ChatAction } from "@/types/api";

const LABELS: Record<string, string> = {
  create_journal_entry: "journal",
  create_expense: "expense",
  create_mood_log: "mood",
  create_sleep_log: "sleep",
  create_caffeine_log: "caffeine",
  create_person: "person",
  create_person_interaction: "interaction",
  create_music_memory: "music",
};

function label(tool: string): string | null {
  if (tool in LABELS) return `+ ${LABELS[tool]}`;
  if (tool === "set_memory_importance") return "importance changed";
  const [verb, ...rest] = tool.split("_");
  const noun = rest.join(" ").replace(/ log$/, "").replace(/ entry$/, "");
  if (verb === "update") return `edited ${noun}`;
  if (verb === "delete") return `deleted ${noun}`;
  return null; // reads and searches are not shown
}

/** Small badges for what the agent changed in a turn. */
export function ChatActionChips({ actions }: { actions: ChatAction[] }) {
  const chips = actions
    .filter((a) => a.ok)
    .map((a) => label(a.tool))
    .filter((l): l is string => l !== null);
  if (chips.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {chips.map((chip, i) => (
        <Badge key={i} variant="outline" className="font-normal text-muted-foreground">
          {chip}
        </Badge>
      ))}
    </div>
  );
}
