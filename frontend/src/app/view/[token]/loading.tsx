// Tab-to-tab navigation inside the client view: the header and tabs stay,
// the page body shows a skeleton until its data arrives.
import { ViewPageSkeleton } from "@/components/view/ViewPageSkeleton"

export default function Loading() {
  return <ViewPageSkeleton />
}
