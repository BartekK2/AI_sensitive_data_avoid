export default function Wordmark({ className = "" }) {
  return (
    <span className={`wordmark ${className}`.trim()}>
      <span className="ai">A</span>eg<span className="ai">I</span>s
    </span>
  );
}
