import Link from "next/link";

const SAMPLE_CHATS = [
  {
    level: "Concept",
    q: "What is the closed-loop model of translation initiation?",
    a: "Great question! The closed-loop model describes how the 5' cap and 3' poly-A tail interact through eIF4G and PABP to circularize the mRNA, enhancing ribosome recycling...",
    badge: "bg-green-100 text-green-800",
  },
  {
    level: "Homework (hint)",
    q: "Question 4: Predict the phenotype when eIF4E is mutated to reduce cap-binding affinity.",
    a: "Before predicting the phenotype, let's think about what eIF4E normally does in the initiation complex. What step would be most directly disrupted by reduced cap-binding?",
    badge: "bg-yellow-100 text-yellow-800",
  },
  {
    level: "Homework (scaffold)",
    q: "I think translation would decrease because the ribosome can't find the mRNA...",
    a: "You're on the right track — cap recognition is indeed the first bottleneck. Let's break it into steps: (1) What recruits eIF4E to the cap? (2) What downstream events depend on that recruitment? Which step are you most unsure about?",
    badge: "bg-orange-100 text-orange-800",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <header className="bg-[#003262] text-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-[#FDB515] font-bold text-xl">MCB Tutor</span>
          <span className="text-sm opacity-70">UC Berkeley</span>
        </div>
        <Link
          href="/login"
          className="bg-[#FDB515] text-[#003262] font-semibold px-4 py-2 rounded-lg text-sm hover:bg-yellow-400 transition-colors"
        >
          Sign in with Berkeley
        </Link>
      </header>

      {/* Hero */}
      <main className="flex-1">
        <section className="bg-gradient-to-b from-[#003262] to-[#004a8f] text-white px-6 py-20 text-center">
          <h1 className="text-4xl font-bold mb-4">Study smarter, not harder.</h1>
          <p className="text-lg opacity-90 max-w-2xl mx-auto mb-8">
            An adaptive AI tutor grounded in your actual MCB course materials — lecture slides,
            handouts, and Ed Discussion threads. It guides your thinking instead of handing you
            answers.
          </p>
          <Link
            href="/login"
            className="inline-block bg-[#FDB515] text-[#003262] font-bold px-8 py-3 rounded-xl text-lg hover:bg-yellow-400 transition-colors"
          >
            Get started — Berkeley SSO
          </Link>
          <p className="text-sm opacity-60 mt-3">Requires @berkeley.edu account</p>
        </section>

        {/* How it works */}
        <section className="max-w-4xl mx-auto px-6 py-16">
          <h2 className="text-2xl font-bold text-[#003262] mb-10 text-center">How it works</h2>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: "01",
                title: "Ask your question",
                desc: "Ask anything — a concept you don't understand, a problem you're stuck on, or exam prep.",
              },
              {
                icon: "02",
                title: "Get guided, not told",
                desc: "The tutor adapts: concept questions get full explanations; homework problems get Socratic hints that escalate as you show effort.",
              },
              {
                icon: "03",
                title: "Grounded in your materials",
                desc: "Every answer cites the actual lecture slides and handouts from your course — no hallucinations, no off-topic detours.",
              },
            ].map((step) => (
              <div key={step.icon} className="text-center">
                <div className="w-12 h-12 rounded-full bg-[#003262] text-white flex items-center justify-center font-bold text-lg mx-auto mb-4">
                  {step.icon}
                </div>
                <h3 className="font-semibold text-lg mb-2">{step.title}</h3>
                <p className="text-slate-600 text-sm leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Sample chats */}
        <section className="bg-slate-50 px-6 py-16">
          <div className="max-w-3xl mx-auto">
            <h2 className="text-2xl font-bold text-[#003262] mb-10 text-center">
              See it in action
            </h2>
            <div className="space-y-6">
              {SAMPLE_CHATS.map((chat, i) => (
                <div key={i} className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                  <span className={`text-xs font-semibold px-2 py-1 rounded-full ${chat.badge} mb-4 inline-block`}>
                    {chat.level}
                  </span>
                  <div className="bg-slate-100 rounded-lg px-4 py-3 text-sm text-slate-700 mb-3">
                    <span className="font-medium text-slate-500 text-xs block mb-1">Student</span>
                    {chat.q}
                  </div>
                  <div className="bg-blue-50 rounded-lg px-4 py-3 text-sm text-slate-700">
                    <span className="font-medium text-blue-600 text-xs block mb-1">MCB Tutor</span>
                    {chat.a}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="bg-[#003262] text-white text-center py-6 text-sm opacity-70">
        UC Berkeley MCB Tutor
      </footer>
    </div>
  );
}
