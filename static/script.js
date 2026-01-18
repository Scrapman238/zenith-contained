async function refresh() {
    const res = await fetch("/api/containers");
    const data = await res.json();
    const tbody = document.getElementById("container-list");
    tbody.innerHTML = '';
    data.forEach(c => {
        tbody.innerHTML += `
            <tr id="container-${c.name}">
                <td>${c.name}</td>
                <td>${c.status}</td>
                <td>
                    <button onclick="start('${c.name}')">Start</button>
                    <button onclick="stop('${c.name}')">Stop</button>
                    <button onclick="restart('${c.name}')">Restart</button>
                    <button onclick="deleteContainer('${c.name}')">Delete</button>
                </td>
            </tr>`;
    });
}

async function start(name) {
    await fetch(`/api/containers/${name}/start`, {method:'POST'});
    refresh();
}
async function stop(name) {
    await fetch(`/api/containers/${name}/stop`, {method:'POST'});
    refresh();
}
async function restart(name) {
    await fetch(`/api/containers/${name}/restart`, {method:'POST'});
    refresh();
}
async function deleteContainer(name) {
    await fetch(`/api/containers/${name}/delete`, {method:'POST'});
    refresh();
}
async function createContainer() {
    const name = document.getElementById("new-name").value;
    if (!name) return alert("Enter a name!");
    await fetch(`/api/containers/new`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({name})
    });
    document.getElementById("new-name").value = '';
    refresh();
}
