import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type TaskStatus = "todo" | "doing" | "done" | "archived";
export type Task = {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: 1 | 2 | 3;
  urgent: boolean;
  progress: number;
  deadline: string | null;
  follow_ups: string[];
  next_follow_up: string | null;
  owner: string;
  depends_on: string;
  position: number;
  done_at: string | null;
  overdue: boolean;
  due_today: boolean;
};
export type TaskBoard = { items: Task[]; top: Task[]; urgent: Task[]; due_today: number };

export const COLUMNS: { status: TaskStatus; label: string }[] = [
  { status: "todo", label: "To do" },
  { status: "doing", label: "In progress" },
  { status: "done", label: "Done" },
];
export const PRIORITY_LABEL: Record<number, string> = { 1: "P1 · Top", 2: "P2 · Normal", 3: "P3 · Low" };

export function useTasks(enabled = true) {
  return useQuery<TaskBoard>({ queryKey: ["tasks"], queryFn: () => api("/tasks"), enabled, staleTime: 10_000 });
}

/** Optimistic update so a drag or a tick feels instant; the board refetches after. */
export function useUpdateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Task> & { id: string }) => api<Task>(`/tasks/${id}`, { method: "PATCH", json: body }),
    onMutate: async ({ id, ...body }) => {
      await qc.cancelQueries({ queryKey: ["tasks"] });
      const prev = qc.getQueryData<TaskBoard>(["tasks"]);
      if (prev) qc.setQueryData<TaskBoard>(["tasks"], { ...prev, items: prev.items.map((t) => (t.id === id ? { ...t, ...body } : t)) });
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(["tasks"], ctx.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export const isoToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
export const shortDate = (d: string | null) => (d ? new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "");
