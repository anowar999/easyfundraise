"use client";

import { Pause, Play, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

type Scene = { img: string; phone?: boolean; title: string; say: string; origin: string };

const SCENES: Scene[] = [
  { img: "/screens/d-investors.webp", title: "Search 14,900+ investors", origin: "30% 30%", say: "Meet EasyFundraise, your personal fundraising agent. Start by searching more than fourteen thousand investors, from angels to seed funds, filtered by sector, stage, cheque size and location." },
  { img: "/screens/d-investors.webp", title: "See why each one fits", origin: "80% 20%", say: "Every investor gets a fit score that explains itself: their thesis, the stage they back, and the deals they did recently." },
  { img: "/screens/d-sequence.webp", title: "Cold emails that sound like you", origin: "50% 40%", say: "Then your agent drafts a short, personal email sequence for each investor, grounded in facts about them, never generic templates." },
  { img: "/screens/d-outreach.webp", title: "Sent from your Gmail, tracked", origin: "40% 25%", say: "Emails go out from your own Gmail, in the investor's time zone. You see opens and replies, and follow-ups stop the moment someone answers." },
  { img: "/screens/d-funnel.webp", title: "Your whole raise in one funnel", origin: "40% 30%", say: "Every conversation lands in a fundraising CRM, from first email to money in the bank. Already have a spreadsheet? Import it in a minute." },
  { img: "/screens/m-funnel.webp", phone: true, title: "Run it from your phone", origin: "50% 30%", say: "On the move? Update a stage, add a note, or check who replied, right from your phone." },
  { img: "/screens/d-home.webp", title: "A brief every morning", origin: "50% 30%", say: "Each morning your agent tells you who to follow up with, which calls need preparing, and who is going cold." },
  { img: "/screens/d-dataroom.webp", title: "A data room that tells you who's interested", origin: "50% 20%", say: "Share a beautiful data room with one link, and see exactly which investors read it, and for how long. Find investors, reach them, and close your round, with EasyFundraise." },
];
const SCENE_MS = 6500;
const FEMALE = /samantha|victoria|karen|moira|tessa|serena|fiona|ava|allison|susan|zira|aria|jenny|libby|sonia|hazel|female|google uk english female|google us english/i;

function pickVoice(): SpeechSynthesisVoice | null {
  const vs = window.speechSynthesis?.getVoices() ?? [];
  const en = vs.filter((v) => v.lang.toLowerCase().startsWith("en"));
  return en.find((v) => /natural|neural|premium|enhanced/i.test(v.name) && FEMALE.test(v.name)) ?? en.find((v) => FEMALE.test(v.name)) ?? en[0] ?? null;
}

/** A narrated product tour built from real screens. Narration uses the browser's own voice, female where available. */
export function Tour() {
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [sound, setSound] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const run = useRef(0);

  const stop = useCallback(() => {
    run.current++;
    if (timer.current) clearTimeout(timer.current);
    window.speechSynthesis?.cancel();
  }, []);

  const playFrom = useCallback(
    (idx: number, withSound: boolean) => {
      stop();
      const id = run.current;
      const go = (k: number) => {
        if (id !== run.current) return;
        if (k >= SCENES.length) {
          setPlaying(false);
          setI(0);
          return;
        }
        setI(k);
        let advanced = false;
        const next = () => {
          if (advanced || id !== run.current) return;
          advanced = true;
          timer.current = setTimeout(() => go(k + 1), 500);
        };
        const synth = window.speechSynthesis;
        if (withSound && synth) {
          const u = new SpeechSynthesisUtterance(SCENES[k].say);
          const v = pickVoice();
          if (v) u.voice = v;
          u.rate = 1.02;
          u.pitch = 1.05;
          u.onend = next;
          u.onerror = next;
          synth.speak(u);
          timer.current = setTimeout(next, Math.max(SCENE_MS, SCENES[k].say.length * 75));
        } else timer.current = setTimeout(next, SCENE_MS);
      };
      setPlaying(true);
      go(idx);
    },
    [stop],
  );

  useEffect(() => {
    window.speechSynthesis?.getVoices();
    const start = () => {
      root.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      playFrom(0, true);
    };
    window.addEventListener("ef:play-tour", start);
    return () => {
      window.removeEventListener("ef:play-tour", start);
      stop();
    };
  }, [playFrom, stop]);

  const s = SCENES[i];
  return (
    <div ref={root} className="relative">
      <div className="relative aspect-[16/10] md:aspect-video rounded-2xl md:rounded-3xl overflow-hidden bg-[#0b1330] ring-1 ring-white/10 shadow-[0_40px_120px_-30px_rgba(15,98,254,0.55)]">
        {SCENES.map((sc, k) => (
          <div key={k} className={`absolute inset-0 transition-opacity duration-700 ${k === i ? "opacity-100" : "opacity-0"}`} aria-hidden={k !== i}>
            {sc.phone ? (
              <div className="absolute inset-0 grid place-items-center bg-[radial-gradient(60%_80%_at_50%_40%,#1d3b8a,#0b1330)]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={sc.img} alt="" loading="lazy" className={`h-[88%] w-auto rounded-[1.6rem] border-[6px] border-[#0b1220] shadow-2xl ${k === i && playing ? "lp-kenburns" : ""}`} />
              </div>
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={sc.img} alt="" loading="lazy" style={{ transformOrigin: sc.origin }} className={`absolute inset-0 w-full h-full object-cover object-top ${k === i && playing ? "lp-kenburns" : ""}`} />
            )}
          </div>
        ))}
        <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-[#070b1a]/90 via-[#070b1a]/40 to-transparent pointer-events-none" />
        <div className="absolute left-4 right-4 md:left-8 md:right-8 bottom-14 md:bottom-16 text-white">
          <div className="text-xs md:text-sm uppercase tracking-[0.18em] text-[#9cc3ff]">
            {i + 1} / {SCENES.length}
          </div>
          <div className="mt-1 text-xl md:text-3xl font-bold tracking-tight">{s.title}</div>
          {playing && <p className="hidden md:block mt-2 max-w-3xl text-white/80 text-[15px] leading-relaxed">{s.say}</p>}
        </div>
        {!playing && (
          <button onClick={() => playFrom(i, sound)} className="absolute inset-0 grid place-items-center group" aria-label="Play the product tour">
            <span className="grid place-items-center w-20 h-20 md:w-24 md:h-24 rounded-full bg-white text-[#0f62fe] shadow-[0_0_0_12px_rgba(255,255,255,0.15)] group-hover:scale-105 transition-transform">
              <Play size={36} fill="currentColor" className="ml-1" />
            </span>
          </button>
        )}
        <div className="absolute left-3 right-3 md:left-6 md:right-6 bottom-3 md:bottom-5 flex items-center gap-3">
          <button className="text-white/90 p-1.5" onClick={() => (playing ? (stop(), setPlaying(false)) : playFrom(i, sound))} aria-label={playing ? "Pause" : "Play"}>
            {playing ? <Pause size={20} /> : <Play size={20} />}
          </button>
          <div className="flex-1 flex gap-1.5">
            {SCENES.map((_, k) => (
              <button key={k} onClick={() => (playing ? playFrom(k, sound) : setI(k))} className="flex-1 h-1.5 rounded-full bg-white/25 overflow-hidden" aria-label={`Scene ${k + 1}`}>
                <span className={`block h-full bg-white ${k < i ? "w-full" : k === i ? (playing ? "lp-progress" : "w-0") : "w-0"}`} style={k === i && playing ? { animationDuration: `${Math.max(SCENE_MS, SCENES[k].say.length * 62)}ms` } : undefined} />
              </button>
            ))}
          </div>
          <button
            className="text-white/90 p-1.5"
            onClick={() => {
              const nv = !sound;
              setSound(nv);
              if (playing) playFrom(i, nv);
            }}
            aria-label={sound ? "Mute narration" : "Turn narration on"}
          >
            {sound ? <Volume2 size={20} /> : <VolumeX size={20} />}
          </button>
        </div>
      </div>
    </div>
  );
}

export function PlayTourButton({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <button className={className} onClick={() => window.dispatchEvent(new Event("ef:play-tour"))}>
      {children}
    </button>
  );
}
