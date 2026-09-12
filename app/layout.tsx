import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { icons: { icon: '/favicon.svg' }, title: '词间 · 四级阅读练习室', description: '选词、阅读、抄写、复习。保存在本地的四级词汇学习档案。' };
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) { return <html lang="zh-CN"><body>{children}</body></html>; }
