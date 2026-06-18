"use client"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer"
import { Separator } from "@/components/ui/separator"
import { formatBytes, formatDate } from "@/lib/api"
import type { Job } from "@/lib/types"

export function JobDetailsDrawer({
  job,
  open,
  onOpenChange,
}: {
  job: Job | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Drawer open={open} onOpenChange={onOpenChange} direction="right">
      <DrawerContent className="sm:max-w-lg">
        <DrawerHeader>
          <DrawerTitle className="font-heading text-3xl">
            {job?.title || "Conversion details"}
          </DrawerTitle>
          <DrawerDescription>Job {job?.id.slice(0, 8)}</DrawerDescription>
        </DrawerHeader>
        {job ? (
          <div className="flex flex-col gap-5 overflow-y-auto px-6 py-4 text-sm">
            <Badge variant="secondary" className="self-start capitalize">
              {job.state}
            </Badge>
            <Separator />
            <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-3">
              <dt className="text-muted-foreground">Format</dt>
              <dd>
                {job.requested_format.toUpperCase()} · {job.requested_quality}
              </dd>
              <dt className="text-muted-foreground">Source</dt>
              <dd className="capitalize">{job.source}</dd>
              <dt className="text-muted-foreground">Created</dt>
              <dd>{formatDate(job.created_at)}</dd>
              <dt className="text-muted-foreground">File size</dt>
              <dd>{formatBytes(job.size_bytes)}</dd>
              <dt className="text-muted-foreground">Expires</dt>
              <dd>{formatDate(job.expires_at)}</dd>
            </dl>
            {job.error_message ? (
              <p className="text-destructive">{job.error_message}</p>
            ) : null}
          </div>
        ) : null}
        <DrawerFooter>
          {job?.artifact_id ? (
            <Button asChild>
              <a href={`/api/v1/artifacts/${job.artifact_id}/download`}>
                Download file
              </a>
            </Button>
          ) : null}
          <DrawerClose asChild>
            <Button variant="outline">Close</Button>
          </DrawerClose>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  )
}
