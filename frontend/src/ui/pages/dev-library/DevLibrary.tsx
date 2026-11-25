import type { ReactNode } from "react";
import { Button, Divider, Frame, Icon, Image, Input, Link, Panel, Select, Text, TextArea } from "@/ui/library";
import type { Hierarchy, TextSize } from "@/ui/library";
import { LightingPicker } from "@/ui/features/settings/LightingPicker";
import "./DevLibrary.css";

/* The /dev/library gallery: every library primitive and Panel material, built from the real components,
 * so the retheme can be reviewed in one place. Mock UI only; deleted with the mock. Grows with each batch. */

const SIZES: TextSize[] = ["xxs", "xs", "s", "base", "m", "l", "xl", "xxl", "display"];
const HIERARCHIES: Hierarchy[] = ["primary", "secondary", "tertiary"];
const FACES = [
  { face: "heading", sample: "Pollen cores, Sea of Galilee" },
  { face: "content", sample: "Drought records line up with the settlement gap." },
  { face: "mono", sample: "CASE NOTES · NODE 1.2.1" },
  { face: "stamp", sample: "Case file" },
] as const;
const ICONS = ["home", "search", "folder", "call_split", "attach_file"];
const OPTIONS = [
  { value: "drought", label: "Drought records" },
  { value: "pollen", label: "Pollen cores" },
  { value: "sediment", label: "Lake sediment" },
];

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <Frame as="section" gap="4">
      <Frame gap="1">
        <Text as="h2" content={title} />
        <Text content={description} hierarchy="tertiary" />
      </Frame>
      <Frame className="dev-library-grid">{children}</Frame>
    </Frame>
  );
}

function Specimen({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <Frame gap="2">
      {children}
      <Text content={caption} face="mono" size="xs" hierarchy="tertiary" />
    </Frame>
  );
}

function IconRow({ hierarchy = "secondary" }: { hierarchy?: Hierarchy }) {
  return (
    <Frame direction="row" gap="3" align="center">
      {ICONS.map((icon) => (
        <Icon key={icon} icon={icon} size="l" hierarchy={hierarchy} />
      ))}
    </Frame>
  );
}

export function DevLibrary() {
  return (
    <Panel as="main" material="cork" scraps="none">
      <Frame gap="8" className="dev-library-column">
        <Frame as="header" gap="2">
          <Text as="h1" content="Library" size="xxl" />
          <Text content="Every primitive and material, in the current theme." hierarchy="tertiary" />
          <Frame direction="row" gap="3" align="center">
            <Text as="span" id="dev-library-lighting" content="Lighting" face="stamp" size="s" />
            <LightingPicker labelledBy="dev-library-lighting" />
          </Frame>
        </Frame>

        <Frame as="section" gap="4">
          <Frame gap="1">
            <Text as="h2" content="Type" />
            <Text content="Every face at every size, then hierarchy and the alert role." hierarchy="tertiary" />
          </Frame>
          <Panel material="paper" stock="paper" edge="clean">
            <Frame gap="6">
              <Frame className="dev-library-grid">
                {FACES.map(({ face, sample }) => (
                  <Frame key={face} gap="2">
                    <Text content={`face="${face}"`} face="mono" size="xs" hierarchy="tertiary" />
                    {SIZES.map((size) => (
                      <Text key={size} content={sample} face={face} size={size} />
                    ))}
                  </Frame>
                ))}
              </Frame>
              <Frame className="dev-library-grid">
                {(["heading", "content"] as const).map((face) =>
                  HIERARCHIES.map((hierarchy) => (
                    <Specimen key={face + hierarchy} caption={`face="${face}" hierarchy="${hierarchy}"`}>
                      <Text content={face === "heading" ? "Pollen cores, Sea of Galilee" : "Drought records line up with the settlement gap."} face={face} hierarchy={hierarchy} size="l" />
                    </Specimen>
                  )),
                )}
                <Specimen caption='role="alert"'>
                  <Text role="alert" content="Node 1.2.1 could not be saved." />
                </Specimen>
              </Frame>
            </Frame>
          </Panel>
        </Frame>

        <Section title="Icon" description="Sizes, hierarchies, then the same row on paper, leather and ink.">
          {SIZES.slice(1, -1).map((size) => (
            <Specimen key={size} caption={`size="${size}"`}>
              <Frame direction="row" gap="3" align="center">
                {ICONS.map((icon) => (
                  <Icon key={icon} icon={icon} size={size} />
                ))}
              </Frame>
            </Specimen>
          ))}
          {HIERARCHIES.map((hierarchy) => (
            <Specimen key={hierarchy} caption={`hierarchy="${hierarchy}"`}>
              <IconRow hierarchy={hierarchy} />
            </Specimen>
          ))}
          <Specimen caption='material="paper"'>
            <Panel material="paper"><IconRow /></Panel>
          </Specimen>
          <Specimen caption='material="leather"'>
            <Panel material="leather"><IconRow /></Panel>
          </Specimen>
          <Specimen caption='material="ink"'>
            <Panel material="ink"><IconRow /></Panel>
          </Specimen>
        </Section>

        <Section title="Panel: hierarchy × elevation" description="Default paper, three hierarchies, flat and floating.">
          {HIERARCHIES.flatMap((hierarchy) =>
            (["flat", "floating"] as const).map((elevation) => (
              <Specimen key={hierarchy + elevation} caption={`hierarchy="${hierarchy}" elevation="${elevation}"`}>
                <Panel hierarchy={hierarchy} elevation={elevation}>
                  <Text content="Drought records" hierarchy={hierarchy} />
                </Panel>
              </Specimen>
            )),
          )}
        </Section>

        <Section title="Paper" description="Stocks, edges, ruling, holes, and torn edges at odd sizes.">
          {(["paper", "card", "card-alt", "slip", "composer"] as const).map((stock) => (
            <Specimen key={stock} caption={`material="paper" stock="${stock}"`}>
              <Panel stock={stock}><Text content="Node 1.2.1" /></Panel>
            </Specimen>
          ))}
          {(["card", "paper"] as const).flatMap((stock) =>
            (["clean", "torn"] as const).map((edge) => (
              <Specimen key={stock + edge} caption={`stock="${stock}" edge="${edge}"`}>
                <Panel stock={stock} edge={edge}><Text content="Pollen cores, Sea of Galilee" /></Panel>
              </Specimen>
            )),
          )}
          {(["none", "lines", "margin"] as const).map((ruled) => (
            <Specimen key={ruled} caption={`stock="slip" ruled="${ruled}"`}>
              <Panel stock="slip" ruled={ruled}>
                <Text content="Check the sediment dates against the drought records." />
              </Panel>
            </Specimen>
          ))}
          <Specimen caption='stock="paper" holes'>
            <Panel stock="paper" holes><Text content="Case notes" /></Panel>
          </Specimen>
          <Specimen caption='stock="card" edge="torn" elevation="floating"'>
            <Panel stock="card" edge="torn" elevation="floating"><Text content="Drought records" /></Panel>
          </Specimen>
          <Specimen caption='edge="torn", tall (~20rem)'>
            <Panel stock="paper" edge="torn" className="dev-library-tall"><Text content="Tall sheet" /></Panel>
          </Specimen>
          <Specimen caption='edge="torn", wide'>
            <Panel stock="paper" edge="torn" className="dev-library-wide"><Text content="Wide sheet" /></Panel>
          </Specimen>
        </Section>

        <Section title="Leather" description="Stitching, pressed, elevation, and a rail strip.">
          {(["dashed", "none"] as const).map((stitch) => (
            <Specimen key={stitch} caption={`material="leather" stitch="${stitch}"`}>
              <Panel material="leather" stitch={stitch}><Text content="Dashboard" /></Panel>
            </Specimen>
          ))}
          {[true, false].map((pressed) => (
            <Specimen key={String(pressed)} caption={`material="leather" pressed={${pressed}}`}>
              <Panel material="leather" pressed={pressed}><Text content="Cases" /></Panel>
            </Specimen>
          ))}
          {(["flat", "floating"] as const).map((elevation) => (
            <Specimen key={elevation} caption={`material="leather" elevation="${elevation}"`}>
              <Panel material="leather" elevation={elevation}><Text content="Cases" /></Panel>
            </Specimen>
          ))}
          <Specimen caption='as="nav" strip with three tertiary icon Buttons'>
            <Panel as="nav" material="leather" className="dev-library-strip">
              <Frame gap="2" align="center">
                <Button hierarchy="tertiary" showIcon showLabel={false} icon="home" label="Dashboard" />
                <Button hierarchy="tertiary" showIcon showLabel={false} icon="folder" label="Cases" pressed />
                <Button hierarchy="tertiary" showIcon showLabel={false} icon="search" label="Search" />
              </Frame>
            </Panel>
          </Specimen>
        </Section>

        <Section title="Ink (flat)" description="The ink Panel with text, tertiary text and an icon.">
          <Specimen caption='material="ink"'>
            <Panel material="ink">
              <Frame gap="2">
                <Text content="Pollen cores, Sea of Galilee" />
                <Text content="CASE NOTES · NODE 1.2.1" hierarchy="tertiary" />
                <Icon icon="call_split" size="l" />
              </Frame>
            </Panel>
          </Specimen>
        </Section>

        <Section title="Cork" description="The board: lamp on or off, scraps, and text straight on the cork.">
          {[true, false].map((lamp) => (
            <Specimen key={String(lamp)} caption={`material="cork" lamp={${lamp}}`}>
              <Panel material="cork" lamp={lamp} className="dev-library-scrap">
                <Text content="Board text, straight on the cork" />
              </Panel>
            </Specimen>
          ))}
          {(["none", "app", "marketing"] as const).map((scraps) => (
            <Specimen key={scraps} caption={`material="cork" scraps="${scraps}"`}>
              <Panel material="cork" scraps={scraps} className="dev-library-scrap">
                <Frame gap="3">
                  <Text content="Drought records" />
                  <Panel material="paper" stock="card" edge="torn" elevation="floating">
                    <Text content="Node 1.2.1" />
                  </Panel>
                </Frame>
              </Panel>
            </Specimen>
          ))}
        </Section>

        <Section title="Fields" description="Input, TextArea and Select; the Panel around a field is its surface.">
          <Specimen caption="Input in a secondary Panel">
            <Panel hierarchy="secondary"><Input placeholder="Search the case" aria-label="Search" /></Panel>
          </Specimen>
          <Specimen caption="TextArea in a secondary Panel">
            <Panel hierarchy="secondary"><TextArea placeholder="Write a note on node 1.2.1" aria-label="Note" /></Panel>
          </Specimen>
          <Specimen caption='Input on material="leather"'>
            <Panel material="leather"><Input placeholder="Case name" aria-label="Case name" /></Panel>
          </Specimen>
          <Specimen caption='Input on material="ink"'>
            <Panel material="ink"><Input placeholder="Ask Gent" aria-label="Ask Gent" /></Panel>
          </Specimen>
          <Specimen caption="Select, three options">
            <Select aria-label="Source" options={OPTIONS} />
          </Specimen>
        </Section>

        <Section title="Divider, Frame, Image, Link" description="The branch divider, Frame gaps, an Image and a Link.">
          <Specimen caption="Divider · Icon · Divider in a row Frame">
            <Frame direction="row" gap="2" align="center">
              <Divider />
              <Icon icon="call_split" />
              <Divider />
            </Frame>
          </Specimen>
          {(["0", "1", "2", "3", "4", "6", "8"] as const).map((gap) => (
            <Specimen key={gap} caption={`Frame gap="${gap}"`}>
              <Frame direction="row" gap={gap}>
                {["1.1", "1.2", "1.3"].map((n) => (
                  <Panel key={n}><Text content={n} face="mono" size="xs" /></Panel>
                ))}
              </Frame>
            </Specimen>
          ))}
          <Specimen caption='Image src="/icon.svg" alt=""'>
            <Image src="/icon.svg" alt="" className="dev-library-thumb" />
          </Specimen>
          <Specimen caption='Link href="/dev/library"'>
            <Link href="/dev/library"><Text content="Back to the top of the library" /></Link>
          </Specimen>
        </Section>
      </Frame>
    </Panel>
  );
}
