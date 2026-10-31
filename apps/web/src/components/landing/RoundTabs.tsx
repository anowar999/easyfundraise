"use client";

import { Check } from "lucide-react";
import { useState } from "react";

const ROUNDS = [
  {
    id: "angel",
    label: "Angel round",
    title: "Raising an angel round",
    body: "Find angel investors and angel syndicates who back your sector, write $10K to $100K cheques and move fast. Track every conversation from first intro to money in the bank.",
    points: ["Angels and syndicates by sector and city", "Short, personal cold emails from your own Gmail", "Round updates that create momentum"],
  },
  {
    id: "pre-seed",
    label: "Pre-seed",
    title: "Raising a pre-seed round",
    body: "Pre-seed is about conviction in the team. We surface pre-seed funds and operator angels who invest before revenue, with the thesis and recent deals that make your email relevant.",
    points: ["Pre-seed VCs that invest before revenue", "Fit score that explains why each investor matches", "A data room you can share in one link"],
  },
  {
    id: "seed",
    label: "Seed",
    title: "Raising a seed round",
    body: "At seed you need a lead and a full round. Filter for investors who lead, line up warm intros, and keep 50+ conversations moving without a spreadsheet.",
    points: ["Seed VCs who lead rounds", "Pipeline from first email to signed", "Meeting briefs before every partner call"],
  },
];

export function RoundTabs() {
  const [active, setActive] = useState("pre-seed");
  return (
    <div>
      <div className="inline-flex rounded-full bg-[#eef3ff] p-1.5" role="tablist" aria-label="Round type">
        {ROUNDS.map((r) => (
          <button
            key={r.id}
            role="tab"
            aria-selected={active === r.id}
            onClick={() => setActive(r.id)}
            className={`rounded-full px-4 md:px-6 h-11 text-[15px] font-semibold transition-all ${active === r.id ? "bg-[#0f62fe] text-white shadow-[0_8px_24px_-8px_rgba(15,98,254,0.7)]" : "text-[#33415c] hover:text-[#0f62fe]"}`}
          >
            {r.label}
          </button>
        ))}
      </div>
      {ROUNDS.map((r) => (
        <div key={r.id} role="tabpanel" hidden={active !== r.id} className="mt-8 grid md:grid-cols-[1.2fr_1fr] gap-8 items-start animate-[lp-fade_.5s_ease]">
          <div>
            <h3 className="text-2xl md:text-3xl font-bold tracking-tight text-[#0b1220]">{r.title}</h3>
            <p className="mt-3 text-lg text-[#4a5670] leading-relaxed">{r.body}</p>
          </div>
          <ul className="space-y-3">
            {r.points.map((p) => (
              <li key={p} className="flex gap-3 text-[17px] text-[#1c2740]">
                <span className="mt-0.5 grid place-items-center w-6 h-6 rounded-full bg-[#16a34a]/12 text-[#16a34a] shrink-0">
                  <Check size={15} strokeWidth={3} />
                </span>
                {p}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
