import type { ComponentProps } from "react";
import "./Image.css";

/* A native <img> for user-supplied pictures (source thumbnails, attachments),
 * which are object URLs or backend URLs with unknown dimensions — the reason
 * this is not next/image. `alt` is required: pass "" for decoration. */

type ImageProps = ComponentProps<"img"> & { alt: string };

export function Image({ alt, ...rest }: ImageProps) {
  // eslint-disable-next-line @next/next/no-img-element -- user content, see above
  return <img alt={alt} {...rest} data-ui="image" />;
}
