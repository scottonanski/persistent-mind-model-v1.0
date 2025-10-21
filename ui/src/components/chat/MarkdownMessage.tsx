"use client";

import { useEffect, useState, useRef } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";

// Configure marked for consistent parsing
marked.setOptions({
  breaks: true,
  gfm: true,
});

interface MarkdownMessageProps {
  text: string;
  isStreaming?: boolean;
}

export function MarkdownMessage({ text, isStreaming = false }: MarkdownMessageProps) {
  const [renderedHtml, setRenderedHtml] = useState("");
  const lastTextRef = useRef("");
  const parsingRef = useRef(false);
  const streamingHtmlRef = useRef(""); // Keep formatted version ready during streaming

  useEffect(() => {
    // Skip if text hasn't changed or we're already parsing
    if (text === lastTextRef.current || parsingRef.current) {
      return;
    }

    lastTextRef.current = text;

    // Parse continuously (even during streaming) but don't render it yet
    if (text?.trim()) {
      parsingRef.current = true;

      try {
        const rawHtml = marked.parse(text, { async: false }) as string;
        const cleanHtml = DOMPurify.sanitize(rawHtml, {
          ALLOWED_TAGS: [
            'p', 'br', 'strong', 'em', 'u', 'code', 'pre',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'blockquote', 'a', 'span', 'div'
          ],
          ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
        });

        if (isStreaming) {
          // Store for instant transition
          streamingHtmlRef.current = cleanHtml;
        } else {
          // Use immediately when not streaming
          setRenderedHtml(cleanHtml);
        }
      } catch (err) {
        console.error("Markdown parsing error:", err);
      } finally {
        parsingRef.current = false;
      }
    }
  }, [text, isStreaming]);

  // When streaming stops, instantly switch to the pre-rendered HTML
  useEffect(() => {
    if (!isStreaming && streamingHtmlRef.current) {
      setRenderedHtml(streamingHtmlRef.current);
      streamingHtmlRef.current = "";
    }
  }, [isStreaming]);

  // During streaming: show plain text with cursor
  if (isStreaming) {
    return (
      <div className="whitespace-pre-wrap text-[0.9375rem] leading-relaxed font-sans">
        {text}
        <span className="inline-block w-[2px] h-[1em] bg-gray-400 animate-pulse align-middle ml-[1px]" />
      </div>
    );
  }

  // After streaming: show formatted markdown (instantly, no flash)
  if (!renderedHtml) {
    // Fallback to plain text only if parsing failed
    return (
      <div className="whitespace-pre-wrap text-[0.9375rem] leading-relaxed">
        {text}
      </div>
    );
  }

  return (
    <div
      className="markdown-content text-[0.9375rem] leading-relaxed"
      dangerouslySetInnerHTML={{ __html: renderedHtml }}
    />
  );
}
