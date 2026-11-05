import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "SCRIPTURA | 합성 데모", description: "합성 데이터로 살펴보는 해석 탐색 데모" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ko"><body>{children}</body></html>;
}
