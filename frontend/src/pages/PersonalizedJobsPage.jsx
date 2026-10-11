import { useParams } from "react-router-dom";
import JobsWorkspace from "../components/personalized/JobsWorkspace";

export default function PersonalizedJobsPage() {
  const { jobId } = useParams();
  return <JobsWorkspace initialJobId={jobId} />;
}
