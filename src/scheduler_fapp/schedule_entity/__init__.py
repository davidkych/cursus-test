import azure.durable_functions as df

def entity(ctx: df.DurableEntityContext):           # noqa: D401
    op    = ctx.operation_name
    state = ctx.get_state(lambda: {})               # {instanceId: {...}}

    if op == "add":
        info = ctx.get_input()
        state[info["instanceId"]] = info

    elif op == "remove":
        instance_id = ctx.get_input()
        state.pop(instance_id, None)

    # NEW ────────────────────────────────────────────────────────────
    elif op == "reset":
        state.clear()                               # wipe everything

    elif op == "list":
        ctx.set_result(state)                       # future extension
    # ────────────────────────────────────────────────────────────────

    ctx.set_state(state)

main = df.Entity.create(entity)
