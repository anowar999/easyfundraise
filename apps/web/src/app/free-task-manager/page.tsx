import { ArrowRight, BellRing, CalendarClock, Check, Flag, LayoutGrid, ListTodo, Pin, Smartphone, Users } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/landing/PageShell";

export const metadata: Metadata = {
  title: { absolute: "Free Task Manager: Simple To-Do List & Priority Board | EasyFundraise" },
  description:
    "A free, simple task manager. Add tasks, set owners, priorities, deadlines and follow-up dates, move them from To do to Done, and see your top 3 and today's tasks every morning. Free forever, no credit card.",
  keywords: ["free task manager", "simple task management tool", "free to-do list app", "priority board", "task tracker for founders", "free kanban board", "monday.com alternative free", "personal task manager"],
  alternates: { canonical: "/free-task-manager" },
  openGraph: {
    title: "Free task manager: stay on top of your tasks",
    description: "Simple to-do list and priority board with owners, deadlines and reminders. Free forever.",
    images: [{ url: "/screens/d-tasks.webp", width: 1600, height: 1000, alt: "Free task manager board" }],
  },
};

const FAQ: [string, string][] = [
  ["Is the task manager really free?", "Yes. My tasks is free for every EasyFundraise user, forever. You don't need a paid plan or a credit card."],
  ["What can I track?", "Each task has a title, a short description, an owner, a status (To do, In progress, Done or Archived), a priority, a deadline, follow-up dates and how much is done."],
  ["Will it remind me?", "Your top 3 tasks and anything due today show on your home screen every time you open the app, and urgent tasks stay pinned on every page until they're done."],
  ["Does it work on my phone?", "Yes. It's built for phones as well as laptops, so you can check and update your tasks anywhere."],
  ["Can my cofounder see my tasks?", "Tasks belong to your workspace, so anyone you invite to it sees the same list and can take ownership of tasks."],
  ["How is it different from monday.com or Trello?", "It's deliberately simple: one list, three columns and the fields that matter. No setup, no templates to learn and no per-seat price."],
];

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "EasyFundraise My tasks",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web, iOS, Android",
    url: "https://easyfundraise.com/free-task-manager",
    description: "Free, simple task manager with owners, priorities, deadlines, follow-up dates and reminders.",
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD", description: "Free forever" },
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQ.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })),
  },
];

const FEATURES: [typeof ListTodo, string, string][] = [
  [LayoutGrid, "Table or sticky notes", "See every task like a spreadsheet, or drag sticky notes from To do to In progress to Done."],
  [Users, "Owners", "Every task is yours by default. Hand it to a cofounder or advisor with one click."],
  [Flag, "Priorities and deadlines", "P1 tasks stand out, and overdue work turns red so nothing slips."],
  [CalendarClock, "Follow-up dates", "Add as many check-back dates as you need. Today's show up first."],
  [BellRing, "Your day at a glance", "Your top 3 and everything due today, the moment you open the app."],
  [Pin, "Urgent stays pinned", "Mark a task urgent and it follows you on every screen until it's done."],
  [Smartphone, "Made for your phone", "Check and update tasks on the go, as easily as on your laptop."],
  [Check, "Progress you can see", "Track % done, and a task moves to Done when it hits 100%."],
];

export default function FreeTaskManager() {
  return (
    <PageShell
      eyebrow="Free task manager"
      title={
        <>
          Stay on top of your tasks. <span className="lp-gradient-text">Free.</span>
        </>
      }
      intro={
        <>
          A simple task manager and priority board. Write it down, decide who owns it and when it&apos;s due, and get reminded. Manage your priorities, stay focused and get more done.
          <div className="mt-8 flex flex-col sm:flex-row sm:items-center gap-3">
            <Link href="/login?mode=signup&next=/app/tasks" className="lp-btn-primary h-14 px-8 text-lg">
              Start free <ArrowRight size={20} />
            </Link>
            <span className="text-[15px] text-white/70">Free forever. No credit card.</span>
          </div>
        </>
      }
    >
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <section className="py-14 md:py-20 bg-white">
        <div className="mx-auto max-w-6xl px-4 md:px-6">
          <div className="rounded-2xl overflow-hidden ring-1 ring-black/5 shadow-[0_30px_80px_-20px_rgba(11,18,32,0.35)]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/screens/d-tasks.webp" alt="Task table with owners, status, priority, deadlines and progress" className="block w-full h-auto" width={1600} height={1000} />
          </div>
          <h2 className="mt-16 text-3xl md:text-5xl font-bold tracking-tight text-[#0b1220]">Everything you need. Nothing you don&apos;t.</h2>
          <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {FEATURES.map(([Icon, t, b]) => (
              <div key={t} className="rounded-2xl border border-[#e7ecf4] p-5">
                <span className="grid place-items-center w-10 h-10 rounded-xl bg-[#0f62fe]/10 text-[#0f62fe]">
                  <Icon size={20} />
                </span>
                <h3 className="mt-4 font-semibold text-[#0b1220]">{t}</h3>
                <p className="mt-1.5 text-[15px] text-[#4a5670] leading-relaxed">{b}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
      <section className="py-14 md:py-20 bg-[#f5f8ff]">
        <div className="mx-auto max-w-6xl px-4 md:px-6 grid md:grid-cols-[1fr_280px] gap-10 items-center">
          <div>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-[#0b1220]">Be more effective. Be more productive.</h2>
            <ol className="mt-6 space-y-4 text-[17px] text-[#1c2740]">
              {["Add a task in one line and press Enter.", "Give it an owner, a priority and a deadline.", "Move it along as you work: To do, In progress, Done.", "Open the app each morning to your top 3 and what's due today."].map((x, i) => (
                <li key={x} className="flex gap-3">
                  <span className="grid place-items-center w-7 h-7 rounded-full bg-[#0f62fe] text-white text-sm font-bold shrink-0">{i + 1}</span>
                  {x}
                </li>
              ))}
            </ol>
          </div>
          <div className="rounded-[2rem] bg-[#0b1220] p-1.5 shadow-[0_30px_80px_-15px_rgba(11,18,32,0.6)] max-w-[260px] mx-auto">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/screens/m-tasks.webp" alt="Task list on a phone" loading="lazy" className="block w-full h-auto rounded-[1.6rem]" width={600} height={1026} />
          </div>
        </div>
      </section>
      <section className="py-14 md:py-20 bg-white">
        <div className="mx-auto max-w-4xl px-4 md:px-6">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-[#0b1220]">Questions</h2>
          <div className="mt-8 divide-y divide-[#e7ecf4]">
            {FAQ.map(([q, a]) => (
              <details key={q} className="py-4 group">
                <summary className="cursor-pointer font-semibold text-[#0b1220] text-lg">{q}</summary>
                <p className="mt-2 text-[#4a5670] leading-relaxed">{a}</p>
              </details>
            ))}
          </div>
          <div className="mt-12 rounded-2xl lp-hero-bg text-white p-8 text-center">
            <h2 className="text-2xl md:text-3xl font-bold">Your priorities, sorted. Free.</h2>
            <p className="mt-2 text-white/75">And when you&apos;re ready to raise, the investor database and AI agent are right there.</p>
            <Link href="/login?mode=signup&next=/app/tasks" className="mt-6 lp-btn-primary h-12 px-7 inline-flex">
              Start managing your tasks <ArrowRight size={18} />
            </Link>
          </div>
        </div>
      </section>
    </PageShell>
  );
}
