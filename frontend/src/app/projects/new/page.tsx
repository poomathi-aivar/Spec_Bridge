import { ProjectForm } from "@/components/ProjectForm";

export default function NewProjectPage() {
  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Create New Project
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Upload one or more business documents (BRDs, SOPs, policies) to generate a
          technical specification. All documents in a project are analyzed together.
        </p>
      </div>
      <ProjectForm />
    </div>
  );
}
