"use client";

import React, { useState, useEffect } from "react";
import { 
  FileUp, 
  Sparkles, 
  Calculator, 
  CheckCircle2, 
  Clock, 
  Loader2, 
  FileText 
} from "lucide-react";
import { useTranslation } from "@/lib/i18n";

interface QuoteExtractionProgressProps {
  isExtracting: boolean;
  fileName?: string;
}

export const QuoteExtractionProgress: React.FC<QuoteExtractionProgressProps> = ({
  isExtracting,
  fileName,
}) => {
  const { t } = useTranslation();
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    if (isExtracting) {
      setElapsedSeconds(0);
      timer = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      if (timer) clearInterval(timer);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isExtracting]);

  const formatTimer = (totalSec: number) => {
    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const stages = [
    {
      id: "doc_validation",
      icon: <FileUp size={16} className="text-blue-500" />,
      title: t("rfq_detail.quote_extraction_progress.stage_1_title"),
      desc: t("rfq_detail.quote_extraction_progress.stage_1_desc"),
    },
    {
      id: "structured_extraction",
      icon: <Sparkles size={16} className="text-emerald-500" />,
      title: t("rfq_detail.quote_extraction_progress.stage_2_title"),
      desc: t("rfq_detail.quote_extraction_progress.stage_2_desc"),
    },
    {
      id: "field_validation",
      icon: <Calculator size={16} className="text-amber-500" />,
      title: t("rfq_detail.quote_extraction_progress.stage_3_title"),
      desc: t("rfq_detail.quote_extraction_progress.stage_3_desc"),
    },
    {
      id: "quote_record",
      icon: <CheckCircle2 size={16} className="text-cyan-500" />,
      title: t("rfq_detail.quote_extraction_progress.stage_4_title"),
      desc: t("rfq_detail.quote_extraction_progress.stage_4_desc"),
    },
  ];

  return (
    <div className="p-4 rounded-xl bg-surface border border-primary/25 shadow-sm space-y-4 animate-in fade-in duration-200">
      {/* Header with Title and Live Timer */}
      <div className="flex items-start justify-between gap-3 pb-3 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 text-primary flex items-center justify-center shrink-0">
            <Sparkles size={16} className="animate-spin text-primary" style={{ animationDuration: "3s" }} />
          </div>
          <div>
            <h4 className="text-xs font-bold text-text-primary">
              {t("rfq_detail.quote_extraction_progress.title")}
            </h4>
            {fileName && (
              <p className="text-[11px] text-text-muted flex items-center gap-1 mt-0.5 font-mono truncate max-w-[220px]">
                <FileText size={12} className="shrink-0" />
                <span className="truncate">{fileName}</span>
              </p>
            )}
          </div>
        </div>

        {/* Live Elapsed Timer */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-surface-elevated border border-border shrink-0 shadow-inner">
          <Clock size={12} className="text-text-muted" />
          <span className="font-mono text-xs font-bold text-primary">
            {formatTimer(elapsedSeconds)}
          </span>
        </div>
      </div>

      {/* 4 Extraction Pipeline Stages */}
      <div className="grid grid-cols-1 gap-2">
        {stages.map((stage, idx) => (
          <div
            key={stage.id}
            className="p-2.5 rounded-lg bg-surface-elevated/70 border border-border/80 flex items-start gap-2.5 transition-colors"
          >
            <div className="w-6 h-6 rounded-md bg-surface border border-border flex items-center justify-center shrink-0 mt-0.5">
              {stage.icon}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-text-primary truncate">
                  {stage.title}
                </span>
                <span className="text-[10px] font-mono font-bold text-text-muted">
                  0{idx + 1}
                </span>
              </div>
              <p className="text-[11px] text-text-muted leading-tight mt-0.5">
                {stage.desc}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Honest Server Processing Notice */}
      <div className="p-2.5 rounded-lg bg-primary/5 border border-primary/15 flex items-start gap-2 text-[11px] text-text-secondary leading-normal">
        <Loader2 size={13} className="animate-spin text-primary shrink-0 mt-0.5" />
        <div className="flex-1">
          <span className={elapsedSeconds > 25 ? "text-text-muted" : "text-text-secondary"}>
            {t("rfq_detail.quote_extraction_progress.initial_hint") || t("rfq_detail.quote_extraction_progress.estimated_hint")}
          </span>
          {elapsedSeconds > 25 && (
            <span className="block text-amber-500 font-medium mt-1">
              {t("rfq_detail.quote_extraction_progress.long_running_hint")}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
