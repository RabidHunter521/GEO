import { Sidebar, MobileSidebar } from "@/components/layout/Sidebar"

export default function ClientsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <MobileSidebar />
        <main className="flex-1 overflow-y-auto bg-app-wash p-4 md:p-6 lg:p-8">
          <div className="mx-auto w-full max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  )
}
