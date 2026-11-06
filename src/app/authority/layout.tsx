import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'SCRIPTURA | 권위와 근거 비교 합성 데모',
  description: '합성 데이터로 공식 채택과 개인 의견, 학술 분석을 구분하는 시범 화면',
};

export default function AuthorityLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
