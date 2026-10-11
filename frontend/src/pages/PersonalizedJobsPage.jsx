import { useParams } from "react-router-dom";
import JobsWorkspace from "../components/personalized/JobsWorkspace";

export default function PersonalizedJobsPage({ external = false }) {
  const { jobId } = useParams();
  return <JobsWorkspace external={external} initialJobId={jobId} />;
}
