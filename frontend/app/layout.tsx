import type { Metadata, Viewport } from 'next';
import Shell from '@/components/Shell';
import './globals.css';

export const metadata: Metadata = {
  title: 'Mr.ceo',
  description: 'Talk to the Manager. Your sub-agents do the work.',
};

export const viewport: Viewport = {
  colorScheme: 'light dark',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
    { media: '(prefers-color-scheme: dark)', color: '#161618' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
