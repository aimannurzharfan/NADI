import logoDark from "@/assets/nadi-logo-dark.svg";
import logoLight from "@/assets/nadi-logo-light.svg";

/** The NADI logo (mark and outlined wordmark), one drawing per theme. Decorative: the link around it carries the name. */
export function NadiLogo() {
  return (
    <>
      <img src={logoLight} alt="" width={92} height={30} className="h-[30px] w-auto dark:hidden" data-logo="light" />
      <img src={logoDark} alt="" width={92} height={30} className="hidden h-[30px] w-auto dark:block" data-logo="dark" />
    </>
  );
}
