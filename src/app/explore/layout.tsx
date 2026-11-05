import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SCRIPTURA | 연구 자료 탐색",
  description: "출처와 검증 상태에 기반한 연구 자료 탐색",
};

export default function ExploreLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
