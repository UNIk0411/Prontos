import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'PRONTOS',
  description: 'Simulation orchestration and scheduling lab',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
