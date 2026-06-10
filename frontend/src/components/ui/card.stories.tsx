import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./card"
import { Button } from "./button"

const meta = {
  title: "UI/Card",
  component: Card,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof Card>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => (
    <Card className="w-80">
      <CardHeader>
        <CardTitle>AI Citability</CardTitle>
        <CardDescription>How likely AI engines are to cite this client</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Seen by AI in 6 of 8 tracked queries this scan.
        </p>
      </CardContent>
      <CardFooter>
        <Button size="sm">View details</Button>
      </CardFooter>
    </Card>
  ),
}
