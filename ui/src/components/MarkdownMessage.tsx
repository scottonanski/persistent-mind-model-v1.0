"use client";

interface MarkdownMessageProps {
  text: string;
  isStreaming?: boolean;
}

export function MarkdownMessage({ text, isStreaming = false }: MarkdownMessageProps) {
  return (
    <div className="whitespace-pre-wrap text-[0.9375rem] leading-relaxed">
      {text}
      {isStreaming && (
        <span className="inline-block w-[2px] h-[1em] bg-gray-400 animate-pulse align-middle ml-[1px]" />
      )}
    </div>
  );
}
