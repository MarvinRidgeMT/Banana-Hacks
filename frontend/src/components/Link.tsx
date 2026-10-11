import type { AnchorHTMLAttributes } from "react";
import { navigate } from "../lib/router";

type Props = { to: string } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">;

/** An in-app hash link. Clicking a link to the current page still counts as a
 * navigation, so it closes the menu, leaves a brush or job screen and scrolls up. */
export function Link({ to, onClick, ...rest }: Props) {
  return (
    <a
      {...rest}
      href={to}
      onClick={(e) => {
        onClick?.(e);
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        navigate(to);
      }}
    />
  );
}
