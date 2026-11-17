import type { NodeMeta } from "@/api/types";
import { Frame, Icon, Text } from "@/ui/library";

/* A question card in the chat history: what was asked, and the answer that led down this thread (ticked: red for the
 * user's, blue for Gent's). The question itself is answered on the card, on the map. Styles: ../Chat.css. */

const said = (a: string | string[]) => (Array.isArray(a) ? a.join(", ") : a);

/** `next`: the thread's next card, which one of this card's answers opened (none: the thread ends here). */
export function QuestionRecord({ node, next }: { node: NodeMeta; next?: string }) {
  const q = node.question!;
  const taken = q.answers.find((a) => a.node_id === next);
  const picked = taken ? (Array.isArray(taken.answer) ? taken.answer : [taken.answer]) : [];
  const own = picked.filter((p) => !q.options.some((o) => o.label === p));
  return (
    <Frame as="li" gap="2" className="question-record" data-by={taken?.by}>
      <Frame direction="row" gap="1" align="center">
        <Icon icon="help" size="s" />
        <Text as="span" size="xxs" className="question-record-kicker" content={q.asker.by === "gent" ? "Gent asked" : "This card's model asked"} />
      </Frame>
      <Text size="s" hierarchy="primary" content={q.prompt} />
      <ul className="question-record-options">
        {q.options.map((o) => {
          const chosen = picked.includes(o.label);
          return (
            <li key={o.label} data-chosen={chosen || undefined}>
              <Icon icon={chosen ? "check" : "remove"} size="s" />
              <Text as="span" size="xs" content={o.label} />
            </li>
          );
        })}
        {own.map((words) => (
          <li key={words} data-chosen>
            <Icon icon="check" size="s" />
            <Text as="span" size="xs" content={`“${words}”`} />
          </li>
        ))}
      </ul>
      {!taken && <Text size="xs" hierarchy="tertiary" content={q.answers.length ? `Answered ${q.answers.map((a) => `“${said(a.answer)}”`).join(", ")} on other branches. Answer on the card, on the map.` : "Answer it on the card, on the map: each answer opens a branch."} />}
    </Frame>
  );
}
