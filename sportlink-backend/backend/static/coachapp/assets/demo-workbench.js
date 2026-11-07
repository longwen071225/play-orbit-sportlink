// Integration hooks for the vendored coach workspace: demoAuth, PortalShell,
// and usePortal. Demo coach selection is local to this browser tab.
const demoCoaches = [
  { id: "coach_wang", phone: "13900000001", name: "王教练" },
  { id: "coach_li", phone: "13900000002", name: "李教练" },
  { id: "coach_zhang", phone: "13900000003", name: "张教练" },
];
const demoAdmin = { id: "", phone: "13700000000" };
const coachSelectionKey = "sportlink-demo-coach";

function selectedCoach() {
  const selectedId = sessionStorage.getItem(coachSelectionKey);
  return demoCoaches.find((coach) => coach.id === selectedId) ?? demoCoaches[0];
}

export async function signInDemoPortal(role, authStore, apiClient) {
  const account = role === "coach" ? selectedCoach() : demoAdmin;
  const session = authStore.getState();
  if (session.token && session.role === role && session.coachId === account.id) {
    return;
  }
  if (session.token) session.logout();

  const { data } = await apiClient.post("/auth/login", {
    phone: account.phone,
    password: "demo123456",
  });
  if (data.user.role.toLowerCase() !== role) {
    throw new Error("演示账号角色不匹配");
  }
  authStore.getState().login(data.token, {
    coachId: account.id,
    coachName: data.user.name,
    role,
  });
}

export function openDemoPortal(path) {
  // Start the new role with fresh data and an empty query cache.
  history.replaceState(null, "", `#${path}`);
  location.reload();
}

export function demoCoachPicker(createElement) {
  return createElement(
    "label",
    { className: "sl-demo-coach" },
    "演示教练",
    createElement(
      "select",
      {
        defaultValue: selectedCoach().id,
        onChange: (event) => {
          sessionStorage.setItem(coachSelectionKey, event.target.value);
          openDemoPortal("/coach/orders");
        },
      },
      demoCoaches.map(({ id, name }) =>
        createElement("option", { key: id, value: id }, name),
      ),
    ),
  );
}

export function orderRefreshOptions(path) {
  if (/^\/(coach|admin)\/orders(?:\/[^/]+)?$/.test(path)) {
    return { refetchInterval: 10_000, refetchOnWindowFocus: "always" };
  }
  return {};
}
