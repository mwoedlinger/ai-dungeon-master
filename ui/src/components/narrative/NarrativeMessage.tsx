import type { NarrativeMessage as NarrativeMessageType } from "../../store/types";
import { MechanicalEvent } from "./MechanicalEvent";
import { ProseBlock } from "./ProseBlock";

interface NarrativeMessageProps {
  message: NarrativeMessageType;
}

export function NarrativeMessage({ message }: NarrativeMessageProps) {
  switch (message.type) {
    case "prose":
      return (
        <div className="animate-fade-in">
          <ProseBlock text={message.text} />
        </div>
      );

    case "player_input":
      return (
        <div className="flex justify-end animate-fade-in">
          <div className="max-w-[75%] px-4 py-2.5 rounded-lg
            bg-gradient-to-r from-accent/8 to-accent/4
            border border-accent/15
            shadow-[0_0_12px_rgba(78,205,196,0.04)]">
            <p className="text-sm text-accent font-['Crimson_Text',serif]">{message.text}</p>
          </div>
        </div>
      );

    case "event":
      return (
        <MechanicalEvent
          eventType={message.eventType ?? "unknown"}
          data={message.eventData ?? {}}
        />
      );

    default:
      return null;
  }
}
