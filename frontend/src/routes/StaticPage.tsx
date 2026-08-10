type StaticPageProps = {
  src: string;
  title: string;
};

export function StaticPage({ src, title }: StaticPageProps) {
  return (
    <main className="landing-embed">
      <iframe src={src} title={title} className="landing-frame" />
    </main>
  );
}
