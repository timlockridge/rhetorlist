//create Tabulator on DOM element with id "example-table"
var table = new Tabulator("#book-list", {
    height:600, // set height of table (in CSS or here), this enables the Virtual DOM and improves render speed dramatically (can be any valid css height value)
    responsiveLayout:"hide",
   selectable:false,
    columns:[ //Define Table Columns
        {title:"Title", field:"title", align:"left", formatter:"link", formatterParams:{urlField:"publisherURL",target:"_blank"}, headerFilter:"input", variableHeight:true},
        {title:"Author(s)", field:"author", align:"left", headerFilter:"input", variableHeight:true},
        {title:"Publisher", field:"publisher", align:"left", headerFilter:"select", headerFilterParams:{
   "":"All",
   "Sweetland Digital Rhetoric Collaborative/UMich Press": "Sweetland DRC/UMichigan Press",
   "Computers and Composition Digital Press/Utah State University Press":"Computers and Composition Digital Press/Utah State University Press",
   "WAC Clearinghouse/UP Colorado":"WAC Clearinghouse/UP Colorado"
}, variableHeight:true},
       {title:"Publication Date", field:"publicationDate", align:"left"},
   {title:"Open Access?", field:"openAccess", align:"left"}
    ]
});

//load data into the table
table.setData("2018.json");