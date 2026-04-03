interface ProseBlockProps {
  text: string;
}

export function ProseBlock({ text }: ProseBlockProps) {
  // Split into paragraphs and apply drop cap to the first one
  const paragraphs = text.split(/\n\n+/);

  return (
    <div className="prose-narrative">
      {paragraphs.map((p, i) => (
        <p
          key={i}
          className={`whitespace-pre-wrap mb-3 last:mb-0 ${i === 0 ? "drop-cap" : ""}`}
        >
          {p}
        </p>
      ))}
    </div>
  );
}
