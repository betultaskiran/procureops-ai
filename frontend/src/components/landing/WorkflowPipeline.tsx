import { 
  FileSearch, 
  Calculator, 
  Database, 
  BrainCircuit, 
  ShieldCheck, 
  UserCheck 
} from "lucide-react";

const PIPELINE_STEPS = [
  {
    id: "01",
    label: "Extraction",
    desc: "Parse PDF Quotes",
    icon: FileSearch,
  },
  {
    id: "02",
    label: "TCO Engine",
    desc: "Exact Cost Math",
    icon: Calculator,
  },
  {
    id: "03",
    label: "Policy RAG",
    desc: "SQL + Vector DB",
    icon: Database,
  },
  {
    id: "04",
    label: "AI Agent",
    desc: "Analyze Trade-offs",
    icon: BrainCircuit,
    isHighlight: true,
  },
  {
    id: "05",
    label: "Verification",
    desc: "Hard Rule Checks",
    icon: ShieldCheck,
  },
  {
    id: "06",
    label: "Approval",
    desc: "Human Sign-off",
    icon: UserCheck,
    isSuccess: true,
  }
];

export function WorkflowPipeline() {
  return (
    <section className="w-full max-w-7xl mx-auto px-6 py-12">
      <div className="text-center mb-10">
        <h2 className="text-sm font-semibold tracking-widest uppercase text-text-muted">
          Under the Hood: The ProcureOps Pipeline
        </h2>
      </div>

      <div className="relative">
        {/* Connecting Line (Background) */}
        <div className="hidden lg:block absolute top-1/2 left-0 w-full h-[2px] bg-border -translate-y-1/2 z-0" />

        {/* Steps Grid */}
        <div className="relative z-10 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-6 lg:gap-4">
          {PIPELINE_STEPS.map((step) => {
            const Icon = step.icon;
            return (
              <div key={step.id} className="flex flex-col items-center text-center bg-bg lg:bg-transparent p-4 lg:p-0 rounded-lg lg:rounded-none">
                
                <div className={`
                  h-14 w-14 rounded-xl flex items-center justify-center border-2 shadow-sm mb-4 transition-all duration-300 hover:scale-105 hover:shadow-md
                  ${step.isHighlight 
                    ? 'bg-ai/10 border-ai text-ai' 
                    : step.isSuccess 
                      ? 'bg-success/10 border-success text-success'
                      : 'bg-surface border-border text-text-primary hover:border-primary'}
                `}>
                  <Icon size={24} />
                </div>
                
                <span className="text-xs font-bold text-text-muted mb-1">{step.id}</span>
                <h3 className="text-sm font-semibold text-text-primary mb-1">{step.label}</h3>
                <p className="text-xs text-text-muted leading-relaxed">{step.desc}</p>
                
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
