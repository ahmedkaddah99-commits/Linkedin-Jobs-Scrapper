import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import termsMarkdown from "../../../docs/legal/RUNR_TERMS_AND_CONDITIONS.md?raw";
import userAgreementMarkdown from "../../../docs/legal/RUNR_USER_AGREEMENT.md?raw";
import "../marketing.css";

const journeySteps = [
  {
    title: "Add your career information",
    copy: "Upload your resume or connect your professional profile. runr. securely parses your experience, skills, and achievements to build a comprehensive candidate profile.",
    image:
      "https://lh3.googleusercontent.com/aida-public/AB6AXuCELFLJrhuDKSo723thfg0o2BFQCykBpdM9p5iYZ3MzaqYLa_qd9C0HG_X_aJCtvnjig-Uldk7wO1cHHk3g1ED3HIjMWceU2ibmbxIruTONaO_Nd2W0UJC3XtPHbLFyNJlB0Db9nIhoRcnKkVJ1o5ZznfYFJzQDy8-oavUTiMQTvaRiWImbsOtBl1Z5D6GA73J3y52Iis3ajN_T6scc-rSh2lZwCVtoAaaGyQwYflkHZtRyViRLvY8S1w",
    alt: "A modern UI mockup showing a user profile import screen.",
  },
  {
    title: "Set your preferences",
    copy: "Define what matters to you. Set precise parameters for role types, salary expectations, remote/hybrid flexibility, and company culture to filter the noise.",
    image:
      "https://lh3.googleusercontent.com/aida-public/AB6AXuBTfMuhkSL_RBBgyoA_yfMH2haNj53seAKWUrb9nQ2l_4TuPF53cgLGALNH_GC0tX9-2_I1lFooX4ZKoucBC9Fklax0BVumKYfa6nkaTiT8_o8xtoUCn4BMQEeDjfd5X8t899edjdH3XrYb2BuJTzzJs0rFwSBDAwc9oGs8U2DL9eyQYHO-_YWgWBtgL1PnVeaJf9xzpfwAomXXh4g0LQDUw7RxiSC5Al3xlwXEhgVBnZJqmJRQySlMMA",
    alt: "A modern UI mockup displaying job preference settings.",
    reverse: true,
  },
  {
    title: "Review your opportunities",
    copy: "Our engine matches your profile and preferences against the market. Review a curated feed of highly relevant roles, complete with 'fit' analysis explaining exactly why you're a strong candidate.",
    image:
      "https://lh3.googleusercontent.com/aida-public/AB6AXuBf-3O8AiYb_iAlbzsoBjJFJBbeXavvmrIkXPaIq1kvhdycfIt3DudNxVIEGpC7QGLN7za2BpUidtleIxHBtTsilrFdOkdDGmMgh3Dqw6ipPvXgWzedsnTZp8n0ZRIeoti7yJLe0rQMcJIwf2hgJ2OJDptnApEyb1IqzcAHA63RohG96trKxKiDx6k-_8p7BYAqMt1wQfSTb-0tWVpxobxhspmPt4Dj-hX9REzBDfv4bLBzAfPPlugiTA",
    alt: "A polished UI mockup of a job opportunity feed.",
  },
  {
    title: "Prepare your application in seconds with AI",
    copy: "Select the most relevant evidence from your profile for a specific role. Our AI instantly drafts a tailored cover letter and highlights pertinent resume bullet points, ready for your final polish.",
    image:
      "https://lh3.googleusercontent.com/aida-public/AB6AXuA0cqrHJvXEcn5GcbUUbrE7s012_Xj4uNq5F5JOg3sEGbOIvwch7yx9lEq3xa9L9kchQseB0rEyFqCuoS5bLD4VYjldBdvmYF4ScFegzNlXcsqLb-gXUf1thCraLigOyAuddWyLoaOPpir6r3s_a1bTWTID9Bfe17GkfMzCbbcDxeFG--MVT16H43bXyWI9L6QjMWro0uHNt0CoxCMNXGEmtlkoWseEOWDywYHjaHY3gcDxpcy_tjk-Zg",
    alt: "An AI-assisted application builder with a document preview.",
    reverse: true,
  },
  {
    title: "Complete the application faster",
    copy: "Use our integrated tools to quickly fill out complex application forms. runr. auto-populates standard fields across various tracking systems, minimizing repetitive data entry.",
    image:
      "https://lh3.googleusercontent.com/aida-public/AB6AXuCfi07K3IpGA0mdzW4wVAJj_jKtxbXiTY7amCwlgLNpJJRcOsihHReAZV63XbYuX9_0y8uXhP3K0I6hMc296VpLkflG-fVvUnWXehXhKsMhn0RI9VFZKtFH2AnigFiOvzkHNiIqfIbHCyor4b8RKoCnWrGJD4pC0LF8ejBzWQTbI_g_rKB34rTcC6fu4oZ5XfTR4RzqFe183cjZryDGfdSMtAuP3B6iXGPiYnglXsxn5pRby7mIleOC1Q",
    alt: "A clean UI mockup showing an autofill feature over an application form.",
  },
  {
    title: "Review and submit",
    copy: "Perform a final review of your meticulously prepared application package. Hit submit, and easily track the status of all your active applications from a central dashboard.",
    image:
      "https://lh3.googleusercontent.com/aida-public/AB6AXuCFTc48virspP08dFpKodHZTYts58BcUPpP3qHHrcFp8_hpWj2CXOp4hdGWnn4KYwyArtnn8r8hky0RTTZYcYsh4J80EuF8_OcEHzYc8nrqAit7qHtaKeX6LFXKc7CXeegGXdL1TCPOrzWm-V1c9U_IgULjv7vtcguakrVaYyAGZD6NMHSapMU3Q2UowSKJyXQ4bNnKqiACiR3WCjLRwMMLXOeDATxB-pcVdTYgeT1ptrmT7pYVEe18Jw",
    alt: "A high-fidelity application tracking dashboard.",
    reverse: true,
  },
];

const freeFeatures = [
  "Unlimited job discovery",
  "Unlimited saved jobs",
  "Unlimited application tracking",
  "Basic autofill on supported application forms",
  "Work experience and employment-date autofill",
  "One career profile",
  "One primary CV",
];

const limitedFeatures = [
  "Limited tailored CV generations",
  "Limited motivation letters",
  "Limited AI application answers",
  "Limited ATS analysis",
];

const sprintFeatures = [
  "Expanded career profile",
  "Full career evidence intelligence",
  "More personalized job matching",
  "Detailed match explanations",
  "Advanced gap analysis",
  "ATS optimization",
  "Role-specific CV tailoring",
  "Multiple CV versions",
  "Motivation letters built from your wider experience",
  "AI answers to common application questions",
  "Advanced Assisted Apply",
  "Remembered application information",
  "Multiple documents and languages",
  "Priority alerts",
  "Advanced application insights",
];

function SiteNav({ active }) {
  const links = [
    ["Product", "/#product"],
    ["How it works", "/#how-it-works"],
    ["Pricing", "/#pricing"],
    ["Security", "/security"],
    ["Help", "/"],
  ];

  return (
    <nav className="marketing-nav">
      <div className="marketing-nav__inner">
        <div className="marketing-nav__left">
          <Link className="marketing-logo" to="/" aria-label="runr. home">
            runr.
          </Link>
          <div className="marketing-nav__links">
            {links.map(([label, href]) => (
              <Link className={active === label ? "is-active" : ""} key={label} to={href}>
                {label}
              </Link>
            ))}
          </div>
        </div>
        <div className="marketing-nav__actions">
          <Link className="marketing-sign-in" to="/sign-in">
            Sign in
          </Link>
          <Link className="marketing-account-button" to="/sign-up">
            {active === "Pricing" ? "Get Started" : "Create account"}
          </Link>
        </div>
      </div>
    </nav>
  );
}

function SiteFooter({ active }) {
  return (
    <footer className="marketing-footer">
      <div className="marketing-footer__inner">
        <div className="marketing-footer__brand">
          <div className="marketing-logo">runr.</div>
          <p>© 2024 runr. Built for performance.</p>
        </div>
        <div className="marketing-footer__links">
          <Link to="/#product">Product</Link>
          <Link className={active === "Pricing" ? "is-active" : ""} to="/#pricing">
            Pricing
          </Link>
          <Link className={active === "Security" ? "is-active" : ""} to="/security">
            Security
          </Link>
          <Link to="/">Help</Link>
          <Link to="/privacy">Privacy Policy</Link>
          <Link to="/terms-and-conditions">Terms of Service</Link>
        </div>
      </div>
    </footer>
  );
}

function ProductSection() {
  return (
    <>
      <section id="product" className="product-hero">
          <div className="product-hero__inner">
            <div className="marketing-kicker">
              <span className="material-symbols-outlined">bolt</span>
              A faster way to move your career forward
            </div>
            <h1>
              Your next opportunity,
              <br />
              ready when you are.
            </h1>
            <p>
              Relevant jobs, ready to apply. Better applications, prepared in minutes. More career
              momentum, less career admin.
            </p>
            <div className="product-hero__actions">
              <Link className="marketing-button marketing-button--primary" to="/sign-up">
                Start for free
              </Link>
              <Link className="marketing-button marketing-button--secondary" to="/#how-it-works">
                See how it works
              </Link>
            </div>

            <div className="hero-visual" aria-label="Runr job matching and application workspace preview">
              <div className="hero-visual__base">
                <div className="hero-visual__browser-bar">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="hero-visual__skeleton">
                  <div className="hero-visual__sidebar">
                    <span className="hero-skeleton hero-skeleton--wide" />
                    <span className="hero-skeleton hero-skeleton--short" />
                    <span className="hero-skeleton hero-skeleton--full" />
                    <span className="hero-skeleton hero-skeleton--medium" />
                  </div>
                  <div className="hero-visual__content">
                    <span className="hero-skeleton hero-skeleton--heading" />
                    <span className="hero-skeleton hero-skeleton--panel" />
                  </div>
                </div>
              </div>
              <div className="hero-floating-card hero-floating-card--match">
                <div className="hero-match-topline">
                  <span className="hero-icon-box">
                    <span className="material-symbols-outlined">corporate_fare</span>
                  </span>
                  <span className="hero-match-badge">94% Match</span>
                </div>
                <h3>Senior Product Designer</h3>
                <p>TechFlow Inc. • Remote</p>
                <div className="hero-tags">
                  <span>SaaS</span>
                  <span>B2B</span>
                </div>
              </div>
              <div className="hero-floating-card hero-floating-card--ready">
                <div className="hero-ready-title">
                  <span className="material-symbols-outlined">auto_awesome</span>
                  <h4>Application Ready</h4>
                </div>
                <div className="hero-ready-list">
                  <span>
                    <span className="material-symbols-outlined">check_circle</span>
                    Tailored CV generated
                  </span>
                  <span>
                    <span className="material-symbols-outlined">check_circle</span>
                    Motivation letter drafted
                  </span>
                </div>
                <button type="button">Review &amp; Submit</button>
              </div>
            </div>
          </div>
      </section>

      <section className="product-feature">
          <div className="product-feature__inner">
            <div className="product-feature__copy">
              <h2>Relevant opportunities, already ready for you.</h2>
              <p>
                Stop scrolling endlessly. runr. surfaces high-quality roles that align with your
                expanded career profile.
              </p>
              <div className="product-feature__reason">
                <span className="product-feature__icon">
                  <span className="material-symbols-outlined">insights</span>
                </span>
                <div>
                  <h3>See why each opportunity fits</h3>
                  <p>Clear reasoning on why a role matches your specific experience and career goals.</p>
                </div>
              </div>
            </div>
            <div className="fit-card">
              <div className="fit-card__header">
                <h4>Why this role fits you</h4>
                <p>Based on your expanded profile</p>
              </div>
              <div className="fit-card__body">
                <div className="fit-card__item">
                  <span className="material-symbols-outlined">task_alt</span>
                  <div>
                    <strong>Requires B2B SaaS Experience</strong>
                    <span>You have 4 years leading B2B product initiatives at Acme Corp.</span>
                  </div>
                </div>
                <div className="fit-card__item">
                  <span className="material-symbols-outlined">task_alt</span>
                  <div>
                    <strong>Growth-stage environment</strong>
                    <span>Matches your preference for scaling teams (Series B-C).</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
      </section>
    </>
  );
}

function HowItWorksSection() {
  return (
    <section id="how-it-works" className="how-page">
        <section className="how-hero">
          <h1>
            The path to your next role, <span>simplified.</span>
          </h1>
          <p>
            runr. eliminates the friction of job hunting. See how our 6-step process turns weeks of
            searching into hours of focused, effective applications.
          </p>
        </section>

        <section className="journey">
          <div className="journey__line" />
          {journeySteps.map((step, index) => (
            <div className={`journey-step${step.reverse ? " journey-step--reverse" : ""}`} key={step.title}>
              <div className="journey-step__copy">
                <div className="journey-step__node">{index + 1}</div>
                <div className="journey-step__card">
                  <span className="journey-step__accent" />
                  <h3>{step.title}</h3>
                  <p>{step.copy}</p>
                </div>
              </div>
              <div className="journey-step__image-wrap">
                <img src={step.image} alt={step.alt} />
              </div>
            </div>
          ))}
        </section>

        <section className="how-cta">
          <h2>Your next opportunity is already waiting.</h2>
          <p>Stop searching and start applying with precision. Join runr. today.</p>
          <Link className="marketing-button marketing-button--primary" to="/sign-up">
            Get Started Now
          </Link>
        </section>
    </section>
  );
}

function FeatureList({ items, muted = false }) {
  return (
    <ul className={muted ? "pricing-list pricing-list--muted" : "pricing-list"}>
      {items.map((item) => (
        <li key={item}>
          <span className="material-symbols-outlined">{muted ? "remove" : "check_circle"}</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function PricingSection() {
  return (
    <section id="pricing" className="pricing-page">
        <header className="pricing-hero">
          <h1>Apply as much as you want</h1>
          <p className="pricing-hero__lead">Runr does not charge you for every application.</p>
          <p>
            The Free plan gives you the tools to discover opportunities, autofill applications, and
            track your progress. Upgrade to Runr Sprint when you want advanced AI personalization,
            deeper career intelligence, and faster application preparation.
          </p>
        </header>
        <div className="pricing-grid">
          <section className="pricing-card pricing-card--free">
            <div>
              <h2>Runr Free</h2>
              <p className="pricing-card__subtitle">Build momentum without paying per application.</p>
              <div className="pricing-card__price">
                <strong>$0</strong>
                <span>/ forever</span>
              </div>
              <FeatureList items={freeFeatures} />
              <FeatureList items={limitedFeatures} muted />
            </div>
            <Link className="pricing-card__button pricing-card__button--secondary" to="/sign-up">
              Start for free
            </Link>
          </section>

          <section className="pricing-card pricing-card--sprint">
            <span className="pricing-card__recommended">Recommended</span>
            <div>
              <h2>Runr Sprint</h2>
              <p className="pricing-card__subtitle">
                Turn every relevant opportunity into a stronger application, faster.
              </p>
              <div className="pricing-card__price">
                <strong>$29</strong>
                <span>/ month</span>
              </div>
              <p className="pricing-card__promise">Unlimited applications. More intelligence behind every one.</p>
              <h3>Everything in Free, plus:</h3>
              <FeatureList items={sprintFeatures} />
            </div>
            <Link className="pricing-card__button pricing-card__button--primary" to="/sign-up">
              Start your Sprint
            </Link>
          </section>
        </div>
    </section>
  );
}

function MarketingHomePage() {
  const { hash } = useLocation();

  useEffect(() => {
    if (!hash) return undefined;
    const target = document.getElementById(decodeURIComponent(hash.slice(1)));
    if (!target) return undefined;
    const frame = window.requestAnimationFrame(() => {
      target.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [hash]);

  return (
    <>
      <SiteNav active="Product" />
      <main className="marketing-home">
        <ProductSection />
        <HowItWorksSection />
        <PricingSection />
      </main>
      <SiteFooter active="Product" />
    </>
  );
}

function SecurityPage() {
  return (
    <>
      <SiteNav active="Security" />
      <main className="security-page">
        <section className="security-hero">
          <div className="marketing-kicker">
            <span className="material-symbols-outlined">shield_lock</span>
            Security &amp; Trust
          </div>
          <h1>Institutional-grade security for your career data.</h1>
          <p>
            We treat your professional history, resumes, and contacts with the operational rigor of a
            modern data platform. Privacy by design, grounded AI, and isolated storage.
          </p>
        </section>

        <section className="security-grid">
          <article className="security-card security-card--auth">
            <div className="security-card__icon">
              <span className="material-symbols-outlined">passkey</span>
            </div>
            <h2>Authentication &amp; Access</h2>
            <p>
              Identity management is offloaded to industry leaders. We leverage Clerk for secure,
              frictionless authentication, ensuring your sessions are protected with modern standards.
            </p>
            <div className="security-card__subgrid">
              <div>
                <span className="material-symbols-outlined">fingerprint</span>
                <h3>MFA Support</h3>
                <p>Multi-factor authentication available for all accounts to secure login.</p>
              </div>
              <div>
                <span className="material-symbols-outlined">history</span>
                <h3>Session Management</h3>
                <p>Active session tracking and automatic timeout enforcement.</p>
              </div>
            </div>
          </article>

          <article className="security-card security-card--ownership">
            <span className="security-card__watermark material-symbols-outlined">database</span>
            <div className="security-card__icon">
              <span className="material-symbols-outlined">vpn_key</span>
            </div>
            <h2>Data Ownership</h2>
            <p>Built on a 'Privacy by Design' architecture. You own your data.</p>
            <ul>
              <li><span className="material-symbols-outlined">check_circle</span>Workspace-scoped access controls isolate your distinct operational environments.</li>
              <li><span className="material-symbols-outlined">check_circle</span>Signed object-download URLs ensure only authorized sessions access documents.</li>
              <li><span className="material-symbols-outlined">check_circle</span>Complete export and deletion capabilities available at any time.</li>
            </ul>
          </article>

          <article className="security-card security-card--half">
            <div className="security-card__icon"><span className="material-symbols-outlined">dns</span></div>
            <h2>Infrastructure &amp; Storage</h2>
            <p>Deployed on enterprise-grade cloud infrastructure utilizing AWS/S3 compatible storage layers.</p>
            <div className="security-inset">
              <span className="material-symbols-outlined">folder_zip</span>
              <div><h3>Isolated Object Storage</h3><p>Career assets (CVs, cover letters) are logically separated from application databases.</p></div>
            </div>
          </article>

          <article className="security-card security-card--half">
            <div className="security-card__icon"><span className="material-symbols-outlined">rule</span></div>
            <h2>Operational Integrity</h2>
            <p>System-to-system communication is verified and audited to maintain data integrity across integrations.</p>
            <div className="security-checks">
              <span><span className="material-symbols-outlined">verified_user</span>Webhook signature verification</span>
              <span><span className="material-symbols-outlined">key</span>API token hashing at rest</span>
              <span><span className="material-symbols-outlined">visibility_off</span>Automated log redaction of sensitive fields</span>
            </div>
          </article>

          <article className="security-card security-card--ai">
            <div className="security-card__ai-icon"><span className="material-symbols-outlined">psychology</span></div>
            <div><h2>Responsible AI Implementation</h2><p>Our AI extraction features are strictly grounded in user-provided documents. We do not use your personal career data to train foundational models. Processing occurs with strict data isolation, ensuring your context remains yours alone.</p></div>
          </article>
        </section>
      </main>
      <SiteFooter active="Security" />
    </>
  );
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
}

function markdownBlocks(markdown) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let list = [];
  let ordered = false;
  let quote = [];

  function flushParagraph() {
    if (paragraph.length) {
      blocks.push({ type: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  }

  function flushList() {
    if (list.length) {
      blocks.push({ type: ordered ? "ordered" : "unordered", items: list });
      list = [];
      ordered = false;
    }
  }

  function flushQuote() {
    if (quote.length) {
      blocks.push({ type: "quote", text: quote.join(" ") });
      quote = [];
    }
  }

  for (const line of lines) {
    const trimmed = line.trim();
    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    const unorderedItem = trimmed.match(/^[-*]\s+(.+)$/);
    const orderedItem = trimmed.match(/^\d+\.\s+(.+)$/);
    const quoteLine = trimmed.match(/^>\s?(.+)$/);

    if (!trimmed) {
      flushParagraph();
      flushList();
      flushQuote();
      continue;
    }
    if (heading) {
      flushParagraph();
      flushList();
      flushQuote();
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }
    if (unorderedItem || orderedItem) {
      flushParagraph();
      flushQuote();
      const isOrdered = Boolean(orderedItem);
      if (list.length && ordered !== isOrdered) flushList();
      ordered = isOrdered;
      list.push((unorderedItem || orderedItem)[1]);
      continue;
    }
    if (quoteLine) {
      flushParagraph();
      flushList();
      quote.push(quoteLine[1]);
      continue;
    }
    flushList();
    flushQuote();
    paragraph.push(trimmed);
  }

  flushParagraph();
  flushList();
  flushQuote();
  return blocks;
}

function LegalDocumentPage({ kind }) {
  const isTerms = kind === "terms";
  const title = isTerms ? "Terms and Conditions" : "User Agreement & Privacy Policy";
  const markdown = isTerms ? termsMarkdown : userAgreementMarkdown;
  const blocks = markdownBlocks(markdown);
  const contents = blocks
    .filter((block) => block.type === "heading" && block.level === 2)
    .slice(0, 8);

  return (
    <>
      <SiteNav />
      <header className="legal-header">
        <div>
          <h1>{title}</h1>
          <p>
            <span className="material-symbols-outlined">calendar_today</span>
            Last updated: [INSERT LAST UPDATED DATE]
          </p>
        </div>
      </header>
      <main className={`legal-layout${isTerms ? " legal-layout--terms" : " legal-layout--agreement"}`}>
        {isTerms && (
          <aside className="legal-sidebar">
            <div>
              <h2><span className="material-symbols-outlined">list_alt</span>Contents</h2>
              <nav>
                {contents.map((block, index) => (
                  <a href={`#legal-section-${index + 1}`} key={block.text}>{block.text}</a>
                ))}
              </nav>
              <div className="legal-sidebar__contact">
                <p>Have questions about these terms?</p>
                <a href="mailto:[INSERT LEGAL CONTACT EMAIL]">
                  Contact Legal Support <span className="material-symbols-outlined">arrow_forward</span>
                </a>
              </div>
            </div>
          </aside>
        )}
        <article className="legal-document">
          <div className="legal-document__draft">
            Draft for legal review — complete the bracketed fields before publishing.
          </div>
          <div className="legal-content">
            {blocks.map((block, index) => {
              if (block.type === "heading") {
                const Heading = block.level === 1 ? "h2" : block.level === 2 ? "h2" : "h3";
                return <Heading id={block.level === 2 ? `legal-section-${contents.findIndex((item) => item.text === block.text) + 1}` : undefined} key={`${block.type}-${index}`} dangerouslySetInnerHTML={{ __html: inlineMarkdown(block.text) }} />;
              }
              if (block.type === "unordered" || block.type === "ordered") {
                const List = block.type === "ordered" ? "ol" : "ul";
                return <List key={`${block.type}-${index}`}>{block.items.map((item) => <li dangerouslySetInnerHTML={{ __html: inlineMarkdown(item) }} key={item} />)}</List>;
              }
              if (block.type === "quote") return <blockquote dangerouslySetInnerHTML={{ __html: inlineMarkdown(block.text) }} key={`${block.type}-${index}`} />;
              return <p dangerouslySetInnerHTML={{ __html: inlineMarkdown(block.text) }} key={`${block.type}-${index}`} />;
            })}
          </div>
          <div className="legal-document__footer">
            <span>End of Document</span>
            {isTerms && (
              <div>
                <button type="button" disabled>
                  <span className="material-symbols-outlined">download</span>Download PDF
                </button>
                <button type="button" disabled>I Accept</button>
              </div>
            )}
          </div>
        </article>
      </main>
      <SiteFooter active={isTerms ? "Terms" : "Privacy"} />
    </>
  );
}

export default function MarketingSite({ page = "product" }) {
  if (page === "home" || page === "product" || page === "how" || page === "pricing") {
    return <div className="marketing-site"><MarketingHomePage /></div>;
  }
  if (page === "security") return <div className="marketing-site"><SecurityPage /></div>;
  if (page === "terms") return <div className="marketing-site"><LegalDocumentPage kind="terms" /></div>;
  if (page === "privacy") return <div className="marketing-site"><LegalDocumentPage kind="privacy" /></div>;
  return <div className="marketing-site"><ProductPage /></div>;
}
