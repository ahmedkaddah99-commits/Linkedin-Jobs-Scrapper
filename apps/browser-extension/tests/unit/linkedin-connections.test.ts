import { describe, expect, it } from "vitest";
import { extractLinkedInConnections, linkedInConnectionsCsv } from "../../src/linkedin/connections";

describe("LinkedIn connections page extraction", () => {
  it("extracts connection cards and serializes them to the existing import contract", () => {
    document.body.innerHTML = `
      <ul>
        <li class="mn-connection-card">
          <a href="https://www.linkedin.com/in/jane-doe"><span class="mn-connection-card__name">Jane Doe</span></a>
          <span class="mn-connection-card__occupation">Engineering Manager at ACME, Inc.</span>
          <time>Connected January 2, 2026</time>
        </li>
        <li class="mn-connection-card">
          <a href="https://www.linkedin.com/in/jane-doe?trk=duplicate">Jane Duplicate</a>
        </li>
      </ul>
    `;

    const snapshot = extractLinkedInConnections(document, "https://www.linkedin.com/mynetwork/invite-connect/connections/");
    expect(snapshot.rows).toHaveLength(1);
    expect(snapshot.rows[0]).toMatchObject({
      firstName: "Jane",
      lastName: "Doe",
      profileUrl: "https://www.linkedin.com/in/jane-doe",
      company: "ACME, Inc.",
      position: "Engineering Manager",
    });
    expect(linkedInConnectionsCsv(snapshot.rows)).toContain(
      'Jane,Doe,https://www.linkedin.com/in/jane-doe,,"ACME, Inc.",Engineering Manager,"Connected January 2, 2026"',
    );
  });
});
