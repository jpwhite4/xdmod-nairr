/**
 * NAIRR Reports Module for XDMoD Portal
 * @author Alex Tovar
 * @date 2025-07-14
 *
 * This module displays NAIRR reports fetched from the `/custom_reports/reports` endpoint.
 * It integrates with XDMoD's main tab panel and allows browsing reports by year/month.
 */

function buildReportUrl(year, month) {
  return XDMoD.REST.prependPathBase(
    `/custom_reports/reports?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}`,
  );
}

XDMoD.Module.NairrReports = function (config) {
  XDMoD.Module.NairrReports.superclass.constructor.call(this, config);
};

Ext.apply(XDMoD.Module.NairrReports, {
  setConfig: function (config, name) {
    Ext.getCmp("main_tab_panel").setActiveTab("nairr_reports");
  },
});

Ext.extend(XDMoD.Module.NairrReports, XDMoD.PortalModule, {
  module_id: "nairr_reports",
  usesToolbar: false,
  lastViewState: null,

  reloadReports: function (year, month) {
    var store = Ext.StoreMgr.get("customReportStore");
    if (!store) return;

    var mainPanel = Ext.getCmp("nairr_reports_main_panel");
    if (mainPanel) {
      mainPanel.setTitle(`NAIRR Reports for ${month} ${year}`);
    }

    store.proxy.conn.url = buildReportUrl(year, month);
    store.load();
  },

  initComponent: function () {
    // -----------------------------
    // Default Params
    const now = new Date();
    const urlParams = new URLSearchParams(window.location.search);
    const defaultYear = urlParams.get("year") || now.getFullYear();
    const defaultMonth =
      urlParams.get("month") ||
      now.toLocaleString("default", { month: "long" });
    const initialUrl = buildReportUrl(defaultYear, defaultMonth);

    const getCustomReportQueryString = () => {
      const params = new URLSearchParams(window.location.search);
      const year = params.get("year") || defaultYear;
      const month = params.get("month") || defaultMonth;
      const out = [];
      if (year) out.push(`year=${encodeURIComponent(year)}`);
      if (month) out.push(`month=${encodeURIComponent(month)}`);
      return out.length ? "?" + out.join("&") : "";
    };

    // -----------------------------
    //
    //
    //
    const reportStore = new Ext.data.JsonStore({
      autoDestroy: true,
      autoLoad: true,
      storeId: "customReportStore",
      root: "report_list",
      idProperty: "name",
      fields: ["name", "version", "title", "description", "timestamp"],
      proxy: new Ext.data.HttpProxy({ url: initialUrl, method: "GET" }),
    });
    const reportContainer = new Ext.Panel({
      id: "nairr_reports_container",
      layout: "auto",
      autoScroll: true,
      region: "center",
      items: [],
      emptyText: `
        <div class="no-reports-container">
          <div class="no-reports-icon">&#9888;</div>
          <div class="no-reports-title">No reports available.</div>
        </div>
      `,
      updateReports: function (records) {
        this.removeAll(true);
        if (!records.length) {
          this.body.update(this.emptyText);
          this.doLayout();
          return;
        }
        this.body.update("");
        Ext.each(records, function (record) {
          const report = record.data;
          const panel = new Ext.Panel({
            title: report.title,
            cls: "custom-report-panel",
            html: `
              <div class="custom-report-thumb-wrap" id="${report.name}">
                <div class="custom-report-thumb">
                  <img src="${XDMoD.REST.prependPathBase("/custom_reports/thumbnail/")}${report.name}${getCustomReportQueryString()}"
                       title="${report.name}" />
                </div>
                <div class="custom-report-thumb-desc">
                  <h2 class="custom-report-thumb-title">${report.title}</h2>
                  <p>Version: ${report.version}</p>
                  <p>${report.description}</p>
                  <p>Created At ${report.timestamp}</p>
                  <div>
                    <p><a href="${XDMoD.REST.prependPathBase("/custom_reports/report/")}${report.name}${getCustomReportQueryString()}" name="${report.name}">Download</a></p>
                  </div>
                </div>
              </div>
            `,
            listeners: {
              afterrender: function (p) {
                p.body.mask("Loading...");
                const img = p.body.dom.querySelector("img");
                if (img) {
                  img.onload = function () {
                    p.body.unmask();
                  };
                  img.onerror = function () {
                    p.body.unmask();
                  };
                } else {
                  p.body.unmask();
                }
              },
            },
          });
          reportContainer.add(panel);
        });
        this.doLayout();
      },
    });

    // UI Components
    const mainArea = new Ext.Panel({
      id: "nairr_reports_main_panel",
      title: `NAIRR Reports for ${defaultMonth} ${defaultYear}`,
      region: "center",
      layout: "fit",
      items: [reportContainer],
    });

    reportContainer.on("afterrender", function () {
      reportStore.on("load", function (store, records) {
        reportContainer.updateReports(records);
      });
    });
    const expandAndSelect = (tree, year, month, clickNode) => {
      const yearNode = tree.getRootNode().findChild("text", String(year));
      if (!yearNode) return;
      yearNode.expand(false, false, function () {
        const monthNode = yearNode.findChild("text", String(month));
        if (!monthNode) return;
        tree.getSelectionModel().select(monthNode);
        monthNode.ensureVisible();
        if (clickNode) monthNode.fireEvent("click", monthNode);
      });
    };

    const leftPanel = new Ext.tree.TreePanel({
      region: "west",
      width: 200,
      collapsible: true,
      title: "Report Directory",
      rootVisible: false,
      loader: new Ext.tree.TreeLoader({
        dataUrl: XDMoD.REST.prependPathBase("/custom_reports/report-directory"),
        requestMethod: "GET",
      }),
      root: new Ext.tree.AsyncTreeNode({ text: "Reports", expanded: true }),
      listeners: {
        click: (node) => {
          if (!node.isLeaf()) return;
          const year = node.parentNode.text;
          const month = node.text;
          if (reportContainer) reportContainer.body.mask("Loading...");

          const newUrl = new URL(window.location.href);
          newUrl.searchParams.set("year", year);
          newUrl.searchParams.set("month", month);
          window.history.replaceState({}, "", newUrl.toString());
          this.reloadReports(year, month);
        },
        render: (tree) => {
          tree.getLoader().on("load", function (loader, node) {
            if (node.isRoot) {
              const params = new URLSearchParams(window.location.search);
              expandAndSelect(
                tree,
                params.get("year") || defaultYear,
                params.get("month") || defaultMonth,
                true,
              );
            }
          });
        },
      },
    });

    // -----------------------------
    // Module Layout & Tab Behavior
    Ext.apply(this, {
      layout: "border",
      items: [leftPanel, mainArea],
      listeners: {
        deactivate: () => {
          const params = new URLSearchParams(window.location.search);
          const year = params.get("year");
          const month = params.get("month");
          if (year && month) this.lastViewState = { year, month };
          const url = new URL(window.location.href);
          url.searchParams.delete("year");
          url.searchParams.delete("month");
          window.history.replaceState({}, "", url.toString());
        },
        activate: () => {
          let year = defaultYear;
          let month = defaultMonth;
          if (this.lastViewState) {
            year = this.lastViewState.year;
            month = this.lastViewState.month;
          }
          const url = new URL(window.location.href);
          url.searchParams.set("year", year);
          url.searchParams.set("month", month);
          window.history.replaceState({}, "", url.toString());
          expandAndSelect(leftPanel, year, month, false);
        },
      },
    });

    XDMoD.Module.NairrReports.superclass.initComponent.apply(this, arguments);
  },
});
