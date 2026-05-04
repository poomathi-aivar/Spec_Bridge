import { ProjectList } from "@/components/ProjectList";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Projects
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            View and manage your SPEC BRIDGE projects.
          </p>
        </div>
      </div>
      <ProjectList />
    </div>
  );
}
